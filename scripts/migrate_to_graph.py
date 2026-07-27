import asyncio
import uuid
import json
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from database import async_session
from models.novel import SettingsDoc, GraphNode, GraphEdge, Novel

async def migrate():
    async with async_session() as session:
        print("Starting migration from SettingsDoc to Graph models...")
        
        # Check if Graph models are ready
        try:
            await session.execute(select(GraphNode).limit(1))
        except Exception as e:
            print(f"Error: Graph models not found in DB. Did you run the alembic migration? {e}")
            return
            
        projects_result = await session.execute(select(Novel.id))
        projects = projects_result.scalars().all()
        
        for project_id in projects:
            print(f"Migrating project {project_id}...")
            docs_res = await session.execute(
                select(SettingsDoc).where(SettingsDoc.project_id == project_id)
            )
            docs = docs_res.scalars().all()
            
            migrated_nodes = 0
            migrated_edges = 0
            
            for doc in docs:
                # 1. Create Node
                node = GraphNode(
                    project_id=project_id,
                    name=doc.name,
                    category=doc.category
                )
                session.add(node)
                await session.flush()  # to get node.id
                migrated_nodes += 1
                
                # 2. Create a generic Edge holding the data
                data_dict = {}
                if doc.data:
                    if isinstance(doc.data, dict):
                        data_dict = doc.data
                    else:
                        try:
                            data_dict = json.loads(doc.data)
                        except:
                            data_dict = {"raw": doc.data}
                
                edge = GraphEdge(
                    project_id=project_id,
                    source_node_id=node.id,
                    target_node_id=None,
                    label="初始设定状态",
                    attributes={
                        "content": doc.content,
                        "data": data_dict
                    },
                    valid_from_chapter=1,
                    valid_to_chapter=None
                )
                session.add(edge)
                migrated_edges += 1
                
            print(f"Project {project_id}: Created {migrated_nodes} nodes and {migrated_edges} edges.")
            
        await session.commit()
        print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate())
