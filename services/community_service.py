from typing import List, Dict, Any
from agents.writing.community_summarizer import CommunitySummarizerAgent

class CommunityService:
    @staticmethod
    def _cluster_graph(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Simple connected components algorithm to cluster nodes based on edges.
        """
        adj_list = {n["id"]: [] for n in nodes}
        node_map = {n["id"]: n for n in nodes}
        
        for e in edges:
            source = e["from"] if "from" in e else e.get("source")
            target = e["to"] if "to" in e else e.get("target")
            if target:
                if source in adj_list and target in adj_list:
                    adj_list[source].append(target)
                    adj_list[target].append(source)
                    
        visited = set()
        clusters = []
        
        for node_id in adj_list:
            if node_id not in visited:
                component_nodes = []
                queue = [node_id]
                visited.add(node_id)
                
                while queue:
                    curr = queue.pop(0)
                    component_nodes.append(node_map[curr])
                    for neighbor in adj_list[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                            
                # Only keep components with more than 1 node
                if len(component_nodes) > 1:
                    component_edges = [
                        e for e in edges 
                        if (e.get("from") or e.get("source")) in [n["id"] for n in component_nodes]
                    ]
                    clusters.append({
                        "nodes": component_nodes,
                        "edges": component_edges
                    })
                    
        return clusters

    @staticmethod
    async def generate_community_summaries(nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], novel_format: str) -> List[Dict[str, str]]:
        """
        Cluster the given graph and use LLM to summarize each community.
        """
        clusters = CommunityService._cluster_graph(nodes, edges)
        
        summarizer = CommunitySummarizerAgent()
        summaries = []
        
        for cluster in clusters:
            if not cluster["nodes"]:
                continue
                
            # adapt keys for summarizer if needed
            sum_nodes = [{"name": n.get("label", n["id"]), "category": n.get("group", "character")} for n in cluster["nodes"]]
            sum_edges = [{"source": e.get("from", e.get("source")), "target": e.get("to", e.get("target")), "label": e.get("label", "相关")} for e in cluster["edges"]]
            
            res = await summarizer.summarize_community(sum_nodes, sum_edges, novel_format=novel_format)
            summaries.append({
                "label": res.get("community_label", "未命名势力"),
                "summary": res.get("summary", ""),
                "nodes": [n["name"] for n in sum_nodes]
            })
            
        return summaries
