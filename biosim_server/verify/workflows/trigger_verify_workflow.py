import asyncio
import uuid

from temporalio.client import Client

from biosim_server.omex_sim.biosim1.models import SourceOmex, BiosimSimulatorSpec
from biosim_server.verify.workflows.omex_verify_workflow import OmexVerifyWorkflow, OmexVerifyWorkflowInput


async def start_workflow() -> None:
    client = await Client.connect("localhost:7233")
    source_omex = SourceOmex(omex_s3_file="path/to/model.omex", name="model_name")
    workflow_id = uuid.uuid4().hex
    handle = await client.start_workflow(
        OmexVerifyWorkflow.run,
        args=[OmexVerifyWorkflowInput(
            source_omex=source_omex,
            user_description="description",
            requested_simulators=[BiosimSimulatorSpec(simulator="vcell", version="latest"),
                                  BiosimSimulatorSpec(simulator="copasi", version="latest")],
            include_outputs=True,
            rTol=1e-6,
            aTol=1e-9,
            observables=["time", "concentration"]
        )],
        task_queue="verification_tasks",
        id=workflow_id,
    )
    print(f"Started workflow with ID: {handle.id}")


if __name__ == "__main__":
    asyncio.run(start_workflow())
