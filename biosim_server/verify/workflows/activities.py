from typing import Optional

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel
from temporalio import activity

from biosim_server.omex_sim.biosim1.models import BiosimSimulationRun
from biosim_server.omex_sim.biosim1.models import Hdf5DataValues, HDF5File
from biosim_server.omex_sim.workflows.biosim_activities import get_hdf5_data, GetHdf5DataInput


class SimulationRunInfo(BaseModel):
    biosim_sim_run: BiosimSimulationRun
    hdf5_file: HDF5File


class GenerateStatisticsInput(BaseModel):
    sim_run_info_list: list[SimulationRunInfo]
    include_outputs: bool
    a_tol: float
    r_tol: float


class DatasetVar(BaseModel):
    dataset_name: str
    var_name: str


class RunData(BaseModel):
    run_id: str
    dataset_name: str
    var_names: list[str]  # list of variables found this run for this dataset
    data: Hdf5DataValues  # n-dim array of data for this run, shape=(len(dataset_vars), len(times))


class ComparisonStatistics(BaseModel):
    dataset_name: str
    simulator_version_i: str  # version of simulator used for run i <simulator_name>:<version>
    simulator_version_j: str  # version of simulator used for run j <simulator_name>:<version>
    var_names: list[str]
    mse: Optional[list[float]] = None
    is_close: Optional[list[bool]] = None
    error_message: Optional[str] = None


class GenerateStatisticsOutput(BaseModel):
    sims_run_info: list[SimulationRunInfo]
    all_dataset_vars: list[DatasetVar]
    comparison_statistics: dict[str, list[list[ComparisonStatistics]]]  # matrix of comparison statistics per dataset
    sim_run_data: Optional[list[RunData]] = None


@activity.defn
async def generate_statistics(gen_stats_input: GenerateStatisticsInput) -> GenerateStatisticsOutput:
    # Gather the data from each run for each dataset
    num_runs = len(gen_stats_input.sim_run_info_list)
    datasets: dict[str, dict[str, Hdf5DataValues]] = {}
    sims_run_data: list[RunData] = []

    for run_index_i in range(num_runs):
        sim_run_info_i = gen_stats_input.sim_run_info_list[run_index_i]
        run_id_i = sim_run_info_i.biosim_sim_run.id
        datasets[run_id_i] = {}
        dataset_names_i = [dataset.name for group in sim_run_info_i.hdf5_file.groups for dataset in group.datasets]
        for dataset_name in dataset_names_i:
            data: Hdf5DataValues = await get_hdf5_data(
                GetHdf5DataInput(simulation_run_id=run_id_i, dataset_name=dataset_name))
            datasets[run_id_i][dataset_name] = data
            var_names = sim_run_info_i.hdf5_file.datasets[dataset_name].sedml_labels
            run_data: RunData = RunData(run_id=run_id_i, dataset_name=dataset_name, var_names=var_names, data=data)
            sims_run_data.append(run_data)

    # collect the list of unique dataset names
    dataset_names: set[str] = set()
    dataset_vars: dict[str, DatasetVar] = {}
    for run_index_i in range(num_runs):
        sim_run_info_j = gen_stats_input.sim_run_info_list[run_index_i]
        for group in sim_run_info_j.hdf5_file.groups:
            for dataset in group.datasets:
                for var_name in dataset.sedml_labels:
                    dataset_var_key = f"{dataset.name}.{var_name}"
                    dataset_vars[dataset_var_key] = DatasetVar(dataset_name=dataset.name, var_name=var_name)
                dataset_names.add(dataset.name)
    # get list of unique dataset_vars by reading the metadata within each dataset

    activity.logger.info(f"Found {len(dataset_names)} unique datasets and {len(dataset_vars)} unique dataset variables")

    # for each unique dataset name, compare the results from run_i with run_j (where i < j)
    comparison_statistics: dict[
        str, list[list[ComparisonStatistics]]] = {}  # matrix of comparison statistics per dataset
    for dataset_name in dataset_names:
        ds_comparison: list[list[ComparisonStatistics]] = []  # holds comparisons for this dataset
        for run_index_i in range(num_runs):
            sim_run_info_i = gen_stats_input.sim_run_info_list[run_index_i]
            run_id_i = sim_run_info_i.biosim_sim_run.id
            results_i: dict[str, Hdf5DataValues] = datasets[run_id_i]
            labels_i = sim_run_info_i.hdf5_file.datasets[dataset_name].sedml_labels
            data_i: Hdf5DataValues = results_i[dataset_name]
            array_i: NDArray[np.float64] = np.array(data_i.values, dtype=np.float64).reshape(data_i.shape)
            simulation_version_i = f"{sim_run_info_i.biosim_sim_run.simulator}:{sim_run_info_i.biosim_sim_run.simulatorVersion}"

            ds_comparison_i: list[ComparisonStatistics] = []  # holds comparisons [i,:] for this dataset

            for run_index_j in range(num_runs):
                sim_run_info_j = gen_stats_input.sim_run_info_list[run_index_j]
                run_id_j = sim_run_info_j.biosim_sim_run.id
                results_j: dict[str, Hdf5DataValues] = datasets[run_id_j]
                labels_j = sim_run_info_j.hdf5_file.datasets[dataset_name].sedml_labels
                simulation_version_j = f"{sim_run_info_j.biosim_sim_run.simulator}:{sim_run_info_j.biosim_sim_run.simulatorVersion}"

                # create a comparison statistics object with default values, add data or error message if needed
                stats_i_j = ComparisonStatistics(simulator_version_i=simulation_version_i,
                                                 simulator_version_j=simulation_version_j, dataset_name=dataset_name,
                                                 var_names=labels_i)  # for runs i,j

                if labels_i != labels_j:
                    stats_i_j.error_message = f"Variables of {simulation_version_i} and {simulation_version_j} do not match, {labels_i} != {labels_j}"
                    activity.logger.error(stats_i_j.error_message)
                    ds_comparison_i.append(stats_i_j)
                    continue

                if dataset_name not in results_i or dataset_name not in results_j:
                    stats_i_j.error_message = f"Dataset {dataset_name} not found in results for {simulation_version_i} or {simulation_version_j}"
                    activity.logger.error(stats_i_j.error_message)
                    ds_comparison_i.append(stats_i_j)
                    continue

                data_j: Hdf5DataValues = results_j[dataset_name]
                array_j: NDArray[np.float64] = np.array(data_j.values, dtype=np.float64).reshape(data_j.shape)  # convert to numpy array

                if array_i.shape != array_j.shape:
                    stats_i_j.error_message = f"Shapes of {simulation_version_i} and {simulation_version_j} do not match, {array_i.shape} != {array_j.shape}"
                    activity.logger.error(stats_i_j.error_message)
                    ds_comparison_i.append(stats_i_j)
                    continue

                # compute statistics
                is_close, mse = await calc_stats(a=array_i, b=array_j,
                                                 r_tol=gen_stats_input.r_tol, a_tol=gen_stats_input.a_tol)
                is_close_list: list[bool] = is_close.tolist()  # type: ignore

                activity.logger.info(
                    f"Comparing {simulation_version_j}:run={run_id_i} and {simulation_version_j}:run={run_id_j} for dataset {dataset_name} MSE: {mse} is_close: {is_close}")

                stats_i_j.mse = mse.tolist()  # type: ignore # convert to list for serialization
                stats_i_j.is_close = is_close_list
                stats_i_j.error_message = None
                ds_comparison_i.append(stats_i_j)
            ds_comparison.append(ds_comparison_i)
        comparison_statistics[dataset_name] = ds_comparison

    gen_stats_output = GenerateStatisticsOutput(sims_run_info=gen_stats_input.sim_run_info_list,
                                                all_dataset_vars=list(dataset_vars.values()),
                                                comparison_statistics=comparison_statistics)
    if gen_stats_input.include_outputs:
        gen_stats_output.sim_run_data = sims_run_data

    return gen_stats_output


async def calc_stats(a: NDArray[np.float64], b: NDArray[np.float64],
                     r_tol: float, a_tol: float) -> tuple[NDArray[np.bool], NDArray[np.float64]]:
    mse = np.mean((a - b) ** 2, axis=1)
    is_close_a_b: NDArray[np.bool] = np.isclose(a, b, rtol=r_tol, atol=a_tol, equal_nan=True).all(axis=1)  # type: ignore
    is_close_b_a: NDArray[np.bool] = np.isclose(a, b, rtol=r_tol, atol=a_tol, equal_nan=True).all(axis=1)  # type: ignore
    is_close = np.logical_and(is_close_a_b, is_close_b_a)
    return is_close, mse
