import json
from pathlib import Path

import pytest

from biosim_server.omex_sim.biosim1.models import HDF5File, BiosimSimulationRun
from biosim_server.verify.workflows.activities import generate_statistics, GenerateStatisticsInput, SimulationRunInfo


@pytest.mark.asyncio
async def test_generate_statistics() -> None:
    run_id_1 = "67817a2eba5a3f02b9f2938d"
    run_id_2 = "67817a2e1f52f47f628af971"

    # read the metadata files
    root_path: Path = Path(__file__).parent.parent.parent
    with open(root_path / "local_data" / f"metadata_{run_id_1}.json") as metadata_file_1:
        metadata_1 = metadata_file_1.read()
        hdf5File_1 = HDF5File.model_validate_json(metadata_1)
    with open(root_path / "local_data" / f"metadata_{run_id_2}.json") as metadata_file_2:
        metadata_2 = metadata_file_2.read()
        hdf5File_2 = HDF5File.model_validate_json(metadata_1)

    # read the sim_run files
    with open(root_path / "local_data" / f"sim_run_{run_id_1}.json") as sim_run_file:
        sim_run_json_1: str = sim_run_file.read()
        sim_run_1 = BiosimSimulationRun(**json.loads(sim_run_json_1))
    with open(root_path / "local_data" / f"sim_run_{run_id_2}.json") as sim_run_file:
        sim_run_json_2: str = sim_run_file.read()
        sim_run_2 = BiosimSimulationRun(**json.loads(sim_run_json_2))

    sim_run_infos = [SimulationRunInfo(biosim_sim_run=sim_run_1, hdf5_file=hdf5File_1),
                 SimulationRunInfo(biosim_sim_run=sim_run_2, hdf5_file=hdf5File_2)]
    gen_stats_input = GenerateStatisticsInput(sim_run_info_list=sim_run_infos, include_outputs=True, a_tol=1e-5, r_tol=1e-4)
    results = await generate_statistics(gen_stats_input=gen_stats_input)
    assert results is not None
