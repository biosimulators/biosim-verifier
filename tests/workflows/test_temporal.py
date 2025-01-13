import asyncio
from datetime import timedelta
from typing import List

import pytest
from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker, UnsandboxedWorkflowRunner


@activity.defn
async def say_hello_activity(name: str) -> str:
    return f"Hello, {name}!"


@workflow.defn
class SayHelloWorkflow:
    @workflow.run
    async def run(self) -> List[str]:
        # Run 5 activities at the same time
        results = await asyncio.gather(
            workflow.execute_activity(say_hello_activity, "user1", start_to_close_timeout=timedelta(seconds=5)),
            workflow.execute_activity(say_hello_activity, "user2", start_to_close_timeout=timedelta(seconds=5)),
            workflow.execute_activity(say_hello_activity, "user3", start_to_close_timeout=timedelta(seconds=5)),
            workflow.execute_activity(say_hello_activity, "user4", start_to_close_timeout=timedelta(seconds=5)),
            workflow.execute_activity(say_hello_activity, "user5", start_to_close_timeout=timedelta(seconds=5)), )
        # Sort the results because they can complete in any order
        return list(sorted(results))


@pytest.mark.asyncio
async def test_simple_workflow(temporal_client: Client) -> None:
    # Run a worker for the workflow
    async with Worker(temporal_client, task_queue="hello-parallel-activity-task-queue", workflows=[SayHelloWorkflow],
            activities=[say_hello_activity], workflow_runner=UnsandboxedWorkflowRunner()):
        result = await temporal_client.execute_workflow(SayHelloWorkflow.run, args=[],
            id="hello-parallel-activity-workflow-id", task_queue="hello-parallel-activity-task-queue", )
        expected_results = ['Hello, user1!', 'Hello, user2!', 'Hello, user3!', 'Hello, user4!', 'Hello, user5!']
        assert result == expected_results


class User(BaseModel):
    name: str
    age: int


@activity.defn
async def get_hello_pydantic_user_data() -> User:
    return User(name="John Doe", age=30)


@workflow.defn
class HelloPydanticWorkflow:
    @workflow.run
    async def run(self) -> User:
        return await workflow.execute_activity(get_hello_pydantic_user_data, args=[],
                                               start_to_close_timeout=timedelta(seconds=5))


@pytest.mark.asyncio
async def test_pydantic_workflow(temporal_client: Client) -> None:
    # Run a worker for the workflow
    async with Worker(temporal_client, task_queue="hello-parallel-activity-task-queue",
            workflows=[HelloPydanticWorkflow], activities=[get_hello_pydantic_user_data],
            workflow_runner=UnsandboxedWorkflowRunner()):
        result = await temporal_client.execute_workflow(HelloPydanticWorkflow.run, args=[],
            id="hello-pydantic-workflow-id", task_queue="hello-parallel-activity-task-queue", )
        expected_results = User(name="John Doe", age=30)
        assert result == expected_results
