from database import Base
from models.knowledge import GraphNode
from models.novel import Job, Novel, SystemSettings
from models.operations import PipelineConfigModel
from models.projects import Chapter


def test_domain_modules_register_all_tables_and_compatibility_exports():
    assert Novel.__tablename__ == "novels"
    assert Chapter.__tablename__ == "chapters"
    assert Job.__tablename__ == "jobs"
    assert GraphNode.__tablename__ == "graph_nodes"
    assert SystemSettings.__tablename__ == "system_settings"
    assert PipelineConfigModel.__tablename__ == "pipeline_configs"
    assert {"novels", "chapters", "jobs", "graph_nodes"}.issubset(Base.metadata.tables)
