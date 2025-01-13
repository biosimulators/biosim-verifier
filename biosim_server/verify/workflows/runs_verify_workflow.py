import logging
from datetime import timedelta
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel
from temporalio import workflow
from temporalio.common import RetryPolicy

from biosim_server.omex_sim.biosim1.models import BiosimSimulationRun
from biosim_server.omex_sim.biosim1.models import BiosimSimulatorSpec, HDF5File
from biosim_server.omex_sim.workflows.biosim_activities import GetSimRunInput, get_hdf5_metadata, GetHdf5MetadataInput
from biosim_server.omex_sim.workflows.biosim_activities import get_sim_run
from biosim_server.verify.workflows.activities import generate_statistics, GenerateStatisticsOutput, \
    GenerateStatisticsInput, SimulationRunInfo


class RunsVerifyWorkflowStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RunsVerifyWorkflowInput(BaseModel):
    user_description: str
    biosimulations_run_ids: list[str]
    include_outputs: bool
    rTol: float
    aTol: float
    observables: Optional[list[str]] = None


class RunsVerifyWorkflowOutput(BaseModel):
    workflow_id: str
    workflow_input: RunsVerifyWorkflowInput
    workflow_status: RunsVerifyWorkflowStatus
    timestamp: str
    actual_simulators: Optional[list[BiosimSimulatorSpec]] = None
    workflow_run_id: Optional[str] = None
    workflow_results: Optional[GenerateStatisticsOutput] = None


@workflow.defn
class RunsVerifyWorkflow:
    verify_input: RunsVerifyWorkflowInput
    verify_output: RunsVerifyWorkflowOutput

    @workflow.init
    def __init__(self, verify_input: RunsVerifyWorkflowInput) -> None:
        self.verify_input = verify_input
        # assert verify_input.workflow_id == workflow.info().workflow_id
        self.verify_output = RunsVerifyWorkflowOutput(workflow_id=workflow.info().workflow_id,
            workflow_input=verify_input, workflow_run_id=workflow.info().run_id,
            workflow_status=RunsVerifyWorkflowStatus.IN_PROGRESS, timestamp=str(workflow.now()))

    @workflow.query(name="get_output")
    async def get_runs_sim_workflow_output(self) -> RunsVerifyWorkflowOutput:
        return self.verify_output

    @workflow.run
    async def run(self, verify_input: RunsVerifyWorkflowInput) -> RunsVerifyWorkflowOutput:
        workflow.logger.setLevel(level=logging.INFO)
        workflow.logger.info("Main workflow started.")

        # verify biosimulation runs are valid and complete and retreive Simulation results metadata
        biosimulation_runs: list[BiosimSimulationRun] = []
        for biosimulation_run_id in verify_input.biosimulations_run_ids:
            biosimulation_run = await workflow.execute_activity(get_sim_run,
                args=[GetSimRunInput(biosim_run_id=biosimulation_run_id)], start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=3))
            biosimulation_runs.append(biosimulation_run)

        workflow.logger.info(f"verified access to completed run ids {verify_input.biosimulations_run_ids}.")

        # Get the HDF5 metadata for each simulation run
        run_data: list[SimulationRunInfo] = []
        for biosimulation_run in biosimulation_runs:
            hdf5_file: HDF5File = await workflow.execute_activity(get_hdf5_metadata,
                args=[GetHdf5MetadataInput(simulation_run_id=biosimulation_run.id)],
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=RetryPolicy(maximum_attempts=100, maximum_interval=timedelta(seconds=5),
                                         backoff_coefficient=2.0))
            run_data.append(SimulationRunInfo(biosim_sim_run=biosimulation_run, hdf5_file=hdf5_file))

        generate_statistics_input = GenerateStatisticsInput(sim_run_info_list=run_data,
                                                            include_outputs=self.verify_input.include_outputs,
                                                            a_tol=self.verify_input.aTol, r_tol=self.verify_input.rTol)
        # Generate comparison report
        generate_statistics_output: GenerateStatisticsOutput = await workflow.execute_activity(generate_statistics,
            arg=generate_statistics_input, start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=100, backoff_coefficient=2.0,
                                     maximum_interval=timedelta(seconds=10)), )
        self.verify_output.workflow_results = generate_statistics_output
        return self.verify_output
