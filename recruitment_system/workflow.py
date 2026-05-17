from recruitment_system.agents.document_extraction import DocumentExtractionAgent
from recruitment_system.agents.interview import InterviewAgent
from recruitment_system.agents.job_matching import JobMatchingAgent
from recruitment_system.agents.resume_intake import ResumeIntakeAgent
from recruitment_system.agents.screening import ScreeningAgent
from recruitment_system.agents.supervisor import SupervisorAgent
from recruitment_system.graph import RecruitmentGraph
from recruitment_system.llm import StructuredLLMClient
from recruitment_system.models import WorkflowState


class RecruitmentWorkflow:
    """Compatibility wrapper around the LangGraph recruitment orchestrator."""

    def __init__(
        self,
        document_agent: DocumentExtractionAgent | None = None,
        resume_intake_agent: ResumeIntakeAgent | None = None,
        matching_agent: JobMatchingAgent | None = None,
        screening_agent: ScreeningAgent | None = None,
        interview_agent: InterviewAgent | None = None,
        supervisor_agent: SupervisorAgent | None = None,
        llm_client: StructuredLLMClient | None = None,
    ) -> None:
        self.graph = RecruitmentGraph(
            document_agent=document_agent,
            resume_intake_agent=resume_intake_agent,
            matching_agent=matching_agent,
            screening_agent=screening_agent,
            interview_agent=interview_agent,
            supervisor_agent=supervisor_agent,
            llm_client=llm_client,
        )

    def run(self, resume_input: str, jd_input: str) -> WorkflowState:
        return self.graph.run(resume_input=resume_input, jd_input=jd_input)
