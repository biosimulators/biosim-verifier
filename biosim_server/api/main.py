import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from temporalio import workflow
from temporalio.client import WorkflowHandle

from biosim_server.omex_sim.biosim1.models import BiosimSimulatorSpec, SourceOmex
from biosim_server.verify.workflows.runs_verify_workflow import RunsVerifyWorkflow, RunsVerifyWorkflowInput, \
    RunsVerifyWorkflowOutput

with workflow.unsafe.imports_passed_through():
    from datetime import datetime, UTC
from pathlib import Path

import dotenv
import uvicorn
from fastapi import FastAPI, File, UploadFile, Query, APIRouter, Depends, HTTPException
from starlette.middleware.cors import CORSMiddleware

from biosim_server.dependencies import get_biosim_service, get_file_service, get_temporal_client, \
    init_standalone, shutdown_standalone
from biosim_server.log_config import setup_logging
from biosim_server.verify.workflows.omex_verify_workflow import OmexVerifyWorkflow, OmexVerifyWorkflowInput, \
    OmexVerifyWorkflowOutput, OmexVerifyWorkflowStatus

logger = logging.getLogger(__name__)
setup_logging(logger)

# -- load dev env -- #
REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
DEV_ENV_PATH = os.path.join(REPO_ROOT, 'assets', 'dev', 'config', '.dev_env')
dotenv.load_dotenv(DEV_ENV_PATH)  # NOTE: create an env config at this filepath if dev

# -- constraints -- #

version_path = os.path.join(
    os.path.dirname(__file__),
    ".VERSION"
)
if os.path.exists(version_path):
    with open(version_path, 'r') as f:
        APP_VERSION = f.read().strip()
else:
    APP_VERSION = "0.0.1"

MONGO_URI = os.getenv("MONGO_URI")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
APP_TITLE = "bsvs-server"
APP_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://127.0.0.1:4200',
    'http://127.0.0.1:4201',
    'http://127.0.0.1:4202',
    'http://localhost:4200',
    'http://localhost:4201',
    'http://localhost:4202',
    'http://localhost:8000',
    'http://localhost:3001',
    'https://biosimulators.org',
    'https://www.biosimulators.org',
    'https://biosimulators.dev',
    'https://www.biosimulators.dev',
    'https://run.biosimulations.dev',
    'https://run.biosimulations.org',
    'https://biosimulations.dev',
    'https://biosimulations.org',
    'https://bio.libretexts.org',
    'https://biochecknet.biosimulations.org'
]
APP_SERVERS: list[dict[str, str]] = [
    # {
    #     "url": "https://biochecknet.biosimulations.org",
    #     "description": "Production server"
    # },
    # {
    #     "url": "http://localhost:3001",
    #     "description": "Main Development server"
    # },
    # {
    #     "url": "http://localhost:8000",
    #     "description": "Alternate Development server"
    # }
]

# -- app components -- #

router = APIRouter()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    await init_standalone()
    yield
    await shutdown_standalone()


app = FastAPI(title=APP_TITLE, version=APP_VERSION, servers=APP_SERVERS, lifespan=lifespan)

# add origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=APP_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])


# -- endpoint logic -- #

@app.get("/")
def root() -> dict[str, str]:
    return {
        'docs': 'https://biochecknet.biosimulations.org/docs'
    }


@app.post(
    "/verify_runs",
    response_model=RunsVerifyWorkflowOutput,
    name="Uniform Time Course Comparison from biosimulation runs",
    operation_id="verify_runs",
    tags=["Verification"],
    dependencies=[Depends(get_temporal_client), Depends(get_file_service)],
    summary="Compare UTC outputs from similar biosimulation.org simulations.")
async def verify_runs(
        workflow_id_prefix: str = Query(default="verification-", description="Prefix for the workflow id."),
        run_ids: list[str] = Query(ddescription="List of simulation run ids from biosimulations.org to compare."),
        include_outputs: bool = Query(default=True,
                                      description="Whether to include the output data on which the comparison is based."),
        user_description: str = Query(..., description="User description of the verification run."),
        rel_tol: float = Query(default=1e-6, description="Relative tolerance to use for proximity comparison."),
        abs_tol: float = Query(default=1e-9, description="Absolute tolerance to use for proximity comparison."),
        observables: Optional[list[str]] = Query(default=None,
                                                 description="List of observables to include in the return data.")
) -> RunsVerifyWorkflowOutput:
    # ---- save omex file to a temporary file and then upload to cloud storage ---- #
    save_dest = Path(os.path.join(os.getcwd(), "temp"))
    save_dest.mkdir(parents=True, exist_ok=True)

    # ---- create workflow input ---- #
    workflow_id = f"{workflow_id_prefix}{uuid.uuid4().hex}"
    runs_verify_workflow_input = RunsVerifyWorkflowInput(
        user_description=user_description,
        biosimulations_run_ids=run_ids,
        include_outputs=include_outputs,
        rTol=rel_tol,
        aTol=abs_tol,
        observables=observables)

    # ---- invoke workflow ---- #
    temporal_client = get_temporal_client()
    assert temporal_client is not None
    workflow_handle: WorkflowHandle[RunsVerifyWorkflowInput, RunsVerifyWorkflowOutput] = await temporal_client.start_workflow(
        RunsVerifyWorkflow.run,  # type: ignore
        args=[runs_verify_workflow_input],
        task_queue="verification_tasks",
        id=workflow_id,
    )
    logger.info(f"started workflow with id {workflow_id}")
    assert workflow_handle.id == workflow_id
    runs_verify_workflow_output: RunsVerifyWorkflowOutput = await workflow_handle.result()
    # ---- return initial workflow output ---- #
    return runs_verify_workflow_output



@app.post(
    "/verify_omex",
    response_model=OmexVerifyWorkflowOutput,
    name="Uniform Time Course Comparison from an OMEX/COMBINE archive",
    operation_id="verify_omex",
    tags=["Verification"],
    dependencies=[Depends(get_temporal_client), Depends(get_file_service)],
    summary="Compare UTC outputs from a deterministic SBML model within an OMEX/COMBINE archive.")
async def verify_omex(
        uploaded_file: UploadFile = File(..., description="OMEX/COMBINE archive containing a deterministic SBML model"),
        workflow_id_prefix: str = Query(default="verification-", description="Prefix for the workflow id."),
        simulators: list[str] = Query(default=["amici", "copasi", "pysces", "tellurium", "vcell"],
                                      description="List of simulators 'name' or 'name:version' to compare."),
        include_outputs: bool = Query(default=True,
                                      description="Whether to include the output data on which the comparison is based."),
        user_description: str = Query(..., description="User description of the verification run."),
        rel_tol: float = Query(default=1e-6, description="Relative tolerance to use for proximity comparison."),
        abs_tol: float = Query(default=1e-9, description="Absolute tolerance to use for proximity comparison."),
        observables: Optional[list[str]] = Query(default=None,
                                                 description="List of observables to include in the return data.")
) -> OmexVerifyWorkflowOutput:
    # ---- save omex file to a temporary file and then upload to cloud storage ---- #
    save_dest = Path(os.path.join(os.getcwd(), "temp"))
    save_dest.mkdir(parents=True, exist_ok=True)
    local_temp_path: Path = await save_uploaded_file(uploaded_file, save_dest)

    file_service = get_file_service()
    assert file_service is not None
    s3_path: str = await file_service.upload_file(local_temp_path, local_temp_path.name)
    local_temp_path.unlink()
    logger.info(f"Uploaded file to S3 at {s3_path}")

    # ---- create workflow input ---- #
    simulator_specs: list[BiosimSimulatorSpec] = []
    for simulator in simulators:
        if ":" in simulator:
            name, version = simulator.split(":")
            simulator_specs.append(BiosimSimulatorSpec(simulator=name, version=version))
        else:
            simulator_specs.append(BiosimSimulatorSpec(simulator=simulator, version=None))
    source_omex = SourceOmex(omex_s3_file=s3_path, name="name")
    workflow_id = f"{workflow_id_prefix}{uuid.uuid4().hex}"
    omex_verify_workflow_input = OmexVerifyWorkflowInput(
        source_omex=SourceOmex(omex_s3_file=s3_path, name="name"),
        user_description=user_description,
        requested_simulators=simulator_specs,
        include_outputs=include_outputs,
        rTol=rel_tol,
        aTol=abs_tol,
        observables=observables)

    # ---- invoke workflow ---- #
    logger.info(f"starting workflow for {source_omex}")
    temporal_client = get_temporal_client()
    assert temporal_client is not None
    workflow_handle = await temporal_client.start_workflow(
        OmexVerifyWorkflow.run,
        args=[omex_verify_workflow_input],
        task_queue="verification_tasks",
        id=workflow_id,
    )
    logger.info(f"started workflow with id {workflow_id}")
    assert workflow_handle.id == workflow_id

    # ---- return initial workflow output ---- #
    omex_verify_workflow_output = OmexVerifyWorkflowOutput(
        workflow_id=workflow_id,
        workflow_input=omex_verify_workflow_input,
        workflow_status=OmexVerifyWorkflowStatus.PENDING,
        timestamp=str(datetime.now(UTC)),
        workflow_run_id=workflow_handle.run_id
    )
    return omex_verify_workflow_output


@app.get(
    "/verify_omex/{workflow_id}",
    response_model=OmexVerifyWorkflowOutput,
    operation_id='get-verify_omex',
    tags=["Results"],
    dependencies=[Depends(get_biosim_service), Depends(get_file_service)],
    summary='get omex-based verification report.')
async def get_verify_omex(workflow_id: str) -> OmexVerifyWorkflowOutput:
    logger.info(f"in get /verify_omex/{workflow_id}")

    try:
        # query temporal for the workflow output
        temporal_client = get_temporal_client()
        assert temporal_client is not None
        workflow_handle = temporal_client.get_workflow_handle(workflow_id=workflow_id, result_type=OmexVerifyWorkflowOutput)
        logger.info(msg=f"workflow_handle: {workflow_handle}")
        workflow_output: OmexVerifyWorkflowOutput = await workflow_handle.query("get_output",
                                                                                result_type=OmexVerifyWorkflowOutput)
        return workflow_output
    except Exception as e2:
        exc_message = str(e2)
        msg = f"error retrieving verification job output with id: {workflow_id}: {exc_message}"
        logger.error(msg, exc_info=e2)
        raise HTTPException(status_code=404, detail=msg)


@app.get(
    "/verify_runs/{workflow_id}",
    response_model=OmexVerifyWorkflowOutput,
    operation_id='get-runs-output',
    tags=["Results"],
    dependencies=[Depends(get_biosim_service), Depends(get_file_service)],
    summary='Get the results of an existing verification run.')
async def get_verify_runs(workflow_id: str) -> OmexVerifyWorkflowOutput:
    logger.info(f"in get /verify_runs/{workflow_id}")

    try:
        # query temporal for the workflow output
        temporal_client = get_temporal_client()
        assert temporal_client is not None
        workflow_handle = temporal_client.get_workflow_handle(workflow_id=workflow_id)
        workflow_output: OmexVerifyWorkflowOutput = await workflow_handle.query("get_output",
                                                                                result_type=OmexVerifyWorkflowOutput)
        return workflow_output
    except Exception as e2:
        exc_message = str(e2)
        msg = f"error retrieving verification job output with id: {workflow_id}: {exc_message}"
        logger.error(msg, exc_info=e2)
        raise HTTPException(status_code=404, detail=msg)


async def save_uploaded_file(uploaded_file2: UploadFile, save_dest: Path) -> Path:
    """Write `fastapi.UploadFile` instance passed by api gateway user to `save_dest`."""
    filename = uploaded_file2.filename or (uuid.uuid4().hex + ".omex")
    file_path = save_dest / filename
    with open(file_path, 'wb') as file:
        contents = await uploaded_file2.read()
        file.write(contents)
    return file_path


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
    logger.info("Server started")
