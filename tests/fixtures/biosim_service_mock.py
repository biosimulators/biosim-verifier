import uuid

from typing_extensions import override

from biosim_server.omex_sim.biosim1.biosim_service import BiosimService
from biosim_server.omex_sim.biosim1.models import Hdf5DataValues, BiosimSimulationRun, HDF5File, BiosimSimulationRunStatus, \
    BiosimSimulatorSpec
from biosim_server.omex_verify.database.models import JobStatus


class ObjectNotFoundError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class BiosimServiceMock(BiosimService):
    sim_runs: dict[str, BiosimSimulationRun] = {}
    hdf5_files: dict[str, HDF5File] = {}
    hdf5_data: dict[str, dict[str, Hdf5DataValues]] = {}

    def __init__(self,
                 sim_runs: dict[str, BiosimSimulationRun] | None = None,
                 hdf5_files: dict[str, HDF5File] | None = None,
                 hdf5_data: dict[str, dict[str, Hdf5DataValues]] | None = None) -> None:
        if sim_runs:
            self.sim_runs = sim_runs
        if hdf5_files:
            self.hdf5_files = hdf5_files
        if hdf5_data:
            self.hdf5_data = hdf5_data

    @override
    async def check_biosim_sim_run_status(self, simulation_run_id: str) -> BiosimSimulationRunStatus:
        sim_run = self.sim_runs[simulation_run_id]
        if sim_run:
            if sim_run.status:
                return BiosimSimulationRunStatus(sim_run.status)
            else:
                return BiosimSimulationRunStatus.UNKNOWN
        else:
            raise ObjectNotFoundError("Simulation run not found")

    @override
    async def run_biosim_sim(self, local_omex_path: str, omex_name: str, simulator_spec: BiosimSimulatorSpec) -> BiosimSimulationRun:
        sim_id = str(uuid.uuid4())
        sim_run = BiosimSimulationRun(
            simulator_spec=simulator_spec,
            simulation_id=sim_id,
            status=BiosimSimulationRunStatus.RUNNING
        )
        self.sim_runs[sim_id] = sim_run
        return sim_run

    @override
    async def get_hdf5_metadata(self, simulation_run_id: str) -> HDF5File:
        hdf5_file = self.hdf5_files[simulation_run_id]
        if hdf5_file:
            return hdf5_file
        else:
            raise ObjectNotFoundError("HDF5 metadata not found")

    @override
    async def get_hdf5_data(self, simulation_run_id: str, dataset_name: str) -> Hdf5DataValues:
        all_hdf5_values: dict[str, Hdf5DataValues] = self.hdf5_data[simulation_run_id]
        if all_hdf5_values:
            return all_hdf5_values[dataset_name]
        else:
            raise ObjectNotFoundError("HDF5 metadata not found")

    @override
    async def close(self) -> None:
        pass
