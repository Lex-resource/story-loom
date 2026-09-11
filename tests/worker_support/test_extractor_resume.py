from types import SimpleNamespace

from services.pipeline_types import ChapterStatus
from worker_support.generation_start_policy import should_resume_extractor


def test_postprocess_failed_chapter_resumes_directly_at_extractor():
    chapter = SimpleNamespace(status=ChapterStatus.POSTPROCESS_FAILED)

    assert should_resume_extractor("extractor", chapter) is True


def test_extractor_resume_does_not_match_unvalidated_draft():
    chapter = SimpleNamespace(status=ChapterStatus.DRAFT)

    assert should_resume_extractor("extractor", chapter) is False
