from enum import StrEnum
from typing import Optional

from pydantic import BaseModel

ATTRIBUTE_VALUE_TYPE = int | float | str | bool | list[str] | list[int] | list[float] | list[bool]


class HDF5Attribute(BaseModel):
    key: str
    value: ATTRIBUTE_VALUE_TYPE


class HDF5Dataset(BaseModel):
    name: str
    shape: list[int]
    attributes: list[HDF5Attribute]

    @property
    def sedml_labels(self) -> list[str]:
        for attr in self.attributes:
            if attr.key == "sedmlDataSetLabels":
                if isinstance(attr.value, list) and all(isinstance(v, str) for v in attr.value):
                    return attr.value  # type: ignore
        return []


class HDF5Group(BaseModel):
    name: str
    attributes: list[HDF5Attribute]
    datasets: list[HDF5Dataset]


class HDF5File(BaseModel):
    filename: str
    id: str
    uri: str
    groups: list[HDF5Group]

    @property
    def datasets(self) -> dict[str, HDF5Dataset]:
        dataset_dict: dict[str, HDF5Dataset] = {}
        for group in self.groups:
            for dataset in group.datasets:
                dataset_dict[dataset.name] = dataset
        return dataset_dict


class Hdf5DataValues(BaseModel):
    # simulation_run_id: str
    # dataset_name: str
    shape: list[int]
    values: list[float]


class BiosimSimulationRunStatus(StrEnum):
    CREATED = 'CREATED'
    QUEUED = 'QUEUED',
    RUNNING = 'RUNNING',
    SKIPPED = 'SKIPPED',
    PROCESSING = 'PROCESSING',
    SUCCEEDED = 'SUCCEEDED',
    FAILED = 'FAILED',
    UNKNOWN = 'UNKNOWN'


class SourceOmex(BaseModel):
    name: str
    omex_s3_file: str


class BiosimSimulatorSpec(BaseModel):
    simulator: str
    version: Optional[str] = None


class BiosimSimulationRunApiRequest(BaseModel):
    name: str  # what does this correspond to?
    simulator: str
    simulatorVersion: str
    maxTime: int  # in minutes
    # email: Optional[str] = None
    # cpus: Optional[int] = None
    # memory: Optional[int] = None (in GB)


class BiosimSimulationRun(BaseModel):
    id: str
    name: str
    simulator: str
    simulatorVersion: str
    status: BiosimSimulationRunStatus
    simulatorDigest: Optional[str] = None
    cpus: Optional[int] = None
    memory: Optional[int] = None         # (in GB)
    maxTime: Optional[int] = None        # (in minutes)
    envVars: Optional[list[str]] = None  # list of environment variables (e.g., ["OMP_NUM_THREADS=4"])
    purpose: Optional[str] = None        # what does this correspond to?
    submitted: Optional[str] = None      # datetime string (e.g. 2025-01-10T19:51:11.424Z)
    updated: Optional[str] = None        # datetime string (e.g. 2025-01-10T19:51:11.424Z)
    projectSize: Optional[int] = None    # (in bytes)
    resultsSize: Optional[int] = None    # (in bytes)
    runtime: Optional[int] = None        # (in milliseconds)
    email: Optional[str] = None


class SimulatorComparison(BaseModel):
    simRun1: BiosimSimulationRun
    simRun2: BiosimSimulationRun
    equivalent: bool
