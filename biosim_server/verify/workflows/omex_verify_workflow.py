import asyncio
import logging
from datetime import timedelta
from enum import StrEnum
from typing import Any, Optional, Coroutine

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.workflow import ChildWorkflowHandle

from biosim_server.omex_sim.biosim1.models import BiosimSimulatorSpec, SourceOmex
from biosim_server.omex_sim.workflows.omex_sim_workflow import OmexSimWorkflow, OmexSimWorkflowInput, \
    OmexSimWorkflowOutput
from biosim_server.verify.workflows.activities import generate_statistics, GenerateStatisticsInput, \
    GenerateStatisticsOutput, SimulationRunInfo


class OmexVerifyWorkflowStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

    def __str__(self) -> str:
        return str(self.value)


class OmexVerifyWorkflowInput(BaseModel):
    source_omex: SourceOmex
    user_description: str
    requested_simulators: list[BiosimSimulatorSpec]
    include_outputs: bool
    rTol: float
    aTol: float
    observables: Optional[list[str]] = None


class OmexVerifyWorkflowOutput(BaseModel):
    workflow_id: str
    workflow_input: OmexVerifyWorkflowInput
    workflow_status: OmexVerifyWorkflowStatus
    timestamp: str
    actual_simulators: Optional[list[BiosimSimulatorSpec]] = None
    workflow_run_id: Optional[str] = None
    workflow_results: Optional[GenerateStatisticsOutput] = None


@workflow.defn
class OmexVerifyWorkflow:
    verify_input: OmexVerifyWorkflowInput
    verify_output: OmexVerifyWorkflowOutput

    @workflow.init
    def __init__(self, verify_input: OmexVerifyWorkflowInput) -> None:
        self.verify_input = verify_input
        # assert verify_input.workflow_id == workflow.info().workflow_id
        self.verify_output = OmexVerifyWorkflowOutput(workflow_id=workflow.info().workflow_id, workflow_input=verify_input,
            workflow_run_id=workflow.info().run_id, workflow_status=OmexVerifyWorkflowStatus.IN_PROGRESS,
            timestamp=str(workflow.now()))

    @workflow.query(name="get_output")
    def get_omex_sim_workflow_output(self) -> OmexVerifyWorkflowOutput:
        return self.verify_output

    @workflow.run
    async def run(self, verify_input: OmexVerifyWorkflowInput) -> OmexVerifyWorkflowOutput:
        workflow.logger.setLevel(level=logging.INFO)
        workflow.logger.info("Main workflow started.")

        # Launch child workflows for each simulator
        child_workflows: list[
            Coroutine[Any, Any, ChildWorkflowHandle[OmexSimWorkflowInput, OmexSimWorkflowOutput]]] = []
        for simulator_spec in verify_input.requested_simulators:
            child_workflows.append(workflow.start_child_workflow(OmexSimWorkflow.run,  # type: ignore
                args=[OmexSimWorkflowInput(source_omex=verify_input.source_omex, simulator_spec=simulator_spec)],
                task_queue="verification_tasks", execution_timeout=timedelta(minutes=10), ))

        workflow.logger.info(f"waiting for {len(child_workflows)} child simulation workflows.")
        # Wait for all child workflows to complete
        child_results: list[ChildWorkflowHandle[OmexSimWorkflowInput, OmexSimWorkflowOutput]] = await asyncio.gather(
            *child_workflows)
        workflow.logger.info(f"Launched {len(child_workflows)} child workflows.")

        run_data: list[SimulationRunInfo] = []
        for child_result in child_results:
            omex_sim_workflow_output = await child_result
            if not child_result.done():
                raise Exception(
                    "Child workflow did not complete successfully, even after asyncio.gather on all workflows")

            if omex_sim_workflow_output.biosim_run is None or omex_sim_workflow_output.hdf5_file is None:
                continue
            run_data.append(SimulationRunInfo(biosim_sim_run=omex_sim_workflow_output.biosim_run, hdf5_file=omex_sim_workflow_output.hdf5_file))

        # Generate comparison report
        generate_statistics_output: GenerateStatisticsOutput = await workflow.execute_activity(generate_statistics,
            arg=GenerateStatisticsInput(sim_run_info_list=run_data, include_outputs=verify_input.include_outputs,
                                        a_tol=verify_input.aTol, r_tol=verify_input.rTol),
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=100, backoff_coefficient=2.0,
                                     maximum_interval=timedelta(seconds=10)), )
        self.verify_output.workflow_results = generate_statistics_output

        # Return the report location
        return self.verify_output
