[8/19/2026 4:18 PM] Barak: # { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *
from dataclasses import dataclass


@allow_storage
@dataclass
class Job:
    client: Address
    worker: Address
    title: str
    requirements: str
    submission_url: str
    status: str
    score: u8
    decision: str
    analysis: str


class AgentEscrow(gl.Contract):

    jobs: TreeMap[u256, Job]
    next_job_id: u256

    def init(self):
        self.next_job_id = u256(1)

    @gl.public.write
    def create_job(
        self,
        worker: str,
        title: str,
        requirements: str,
    ):
        worker_address = Address(worker)

        job = Job(
            client=gl.message.sender_address,
            worker=worker_address,
            title=title,
            requirements=requirements,
            submission_url="",
            status="OPEN",
            score=u8(0),
            decision="PENDING",
            analysis="",
        )

        self.jobs[self.next_job_id] = job
        self.next_job_id += 1

    @gl.public.write
    def submit_work(self, job_id: u256, submission_url: str):

        if job_id not in self.jobs:
            raise Exception("JOB_NOT_FOUND")

        job = gl.storage.copy_to_memory(self.jobs[job_id])

        if job.status != "OPEN":
            raise Exception("JOB_NOT_OPEN")

        if gl.message.sender_address != job.worker:
            raise Exception("NOT_ASSIGNED_WORKER")

        job.submission_url = submission_url
        job.status = "SUBMITTED"

        self.jobs[job_id] = job

    @gl.public.write
    def evaluate_submission(self, job_id: u256):

        if job_id not in self.jobs:
            raise Exception("JOB_NOT_FOUND")

        job = gl.storage.copy_to_memory(self.jobs[job_id])

        if job.status != "SUBMITTED":
            raise Exception("NOT_SUBMITTED")

        title = job.title
        requirements = job.requirements
        submission_url = job.submission_url

        def leader_fn():

            page = gl.nondet.web.get(submission_url)

            prompt = f"""
You are evaluating work submitted for an AI-agent job.

JOB TITLE:
{title}

REQUIREMENTS:
{requirements}

SUBMISSION:
{page.body.decode("utf-8")}

Evaluate whether the submission satisfies the requirements.

Return JSON only:
{{
    "decision": "APPROVED" or "REJECTED",
    "score": integer from 0 to 100,
    "analysis": "short explanation"
}}

APPROVED means the submission substantially satisfies the requirements.
REJECTED means important requirements are missing.
"""

            result = gl.nondet.exec_prompt(
                prompt,
                response_format="json"
            )

            if not isinstance(result, dict):
                raise Exception("INVALID_LLM_RESULT")

            decision = result.get("decision")
            score = result.get("score")
            analysis = result.get("analysis")

            if decision not in ("APPROVED", "REJECTED"):
                raise Exception("INVALID_DECISION")

            if not isinstance(score, int) or score < 0 or score > 100:
                raise Exception("INVALID_SCORE")

            return {
                "decision": decision,
                "score": score,
                "analysis": analysis,
            }

        def validator_fn(leader_result) -> bool:

            if not isinstance(leader_result, gl.vm.Return):
                return False

            validator_result = leader_fn()

            leader_data = leader_result.calldata

            # Validators independently perform the same evaluation.
            # Reasoning may differ, but the settlement decision must agree.
            if leader_data["decision"] != validator_result["decision"]:
                return False

            # Allow small differences in subjective scoring.
            return abs(
                leader_data["score"] - validator_result["score"]
            ) <= 10

        result = gl.vm.run_nondet_unsafe(
            leader_fn,
            validator_fn
        )
[8/19/2026 4:18 PM] Barak: # Storage changes happen only AFTER consensus.
        job.status = result["decision"]
        job.decision = result["decision"]
        job.score = u8(result["score"])
        job.analysis = result["analysis"]

        self.jobs[job_id] = job

    @gl.public.view
    def get_job(self, job_id: u256) -> Job:
        if job_id not in self.jobs:
            raise Exception("JOB_NOT_FOUND")

        return self.jobs[job_id]

    @gl.public.view
    def get_next_job_id(self) -> u256:
        return self.next_job_id
