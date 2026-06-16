import chromadb
from ui_aloha.act.gui_agent.planner.trajectory_manager import TrajectoryManager
from sentence_transformers import SentenceTransformer
import os


class ExperienceTable:
    def __init__(self, trajectory_manager: TrajectoryManager, db_path='./chromadb',embed_model='Qwen/Qwen3-Embedding-0.6B'):
        self.trajectory_manager = trajectory_manager
        self.client=chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(name="experience_table")
        self.embed_model=SentenceTransformer(embed_model)
    
    def add_single_experience(self, trace_name,task_description=""):
        trace=self.trajectory_manager.get_full_trace(trace_name)
        trace_data=self.trajectory_manager.get_trajectory_in_context(trace_name, formatting_string=True)
        task_description=trace.get("task_description","")
        if trace_data is None:
            print(f"No trace data found for trace name: {trace_name}")
            return
        if task_description=="":
            task_description=trace_name.replace("_trace","").replace("_"," ")
        ids=[trace_name]
        total_steps=len(trace_data.splitlines())
        metadatas=[]
        metadatas.append({
            "trace_name": trace_name,
            "total_steps": total_steps,
            "success_flag": True,
            "quality_tag": 'manual_high'
            })
        embeddings=self.embed_model.encode(task_description,normalize_embeddings=True).tolist()
        self.collection.add(ids=ids,embeddings=embeddings,metadatas=metadatas,documents=[task_description])
        print('Add successfully!')
    
    def add_experiences_from_directory(self, dir):
        for filename in os.listdir(dir):
            if filename.endswith("_trace.json"):
                trace_name=filename.replace(".json","")
                self.add_single_experience(trace_name)

    def query_experience(self, query, top_k=3):
        q_emb=self.embed_model.encode([query],normalize_embeddings=True).tolist()
        results=self.collection.query(
            query_embeddings=q_emb,
            n_results=top_k,
            where={"$and": [{"quality_tag": 'manual_high'}, {"success_flag": True}]},
            include=["documents", "metadatas", "distances"]
        )
        guidance_trajectories=[]
        for i,(document,metadata, distance) in enumerate(zip(results["documents"][0], results["metadatas"][0], results["distances"][0])):
            if distance<1.0:  # filter out results that are too far
                print(f"Found relevant experience: {document} (distance: {distance:.4f})")
                trace_name= metadata["trace_name"]
                actions=self.trajectory_manager.get_trajectory_in_context(trace_name, formatting_string=True)
                example=f'Example {i+1} (distance: {distance:.4f}):\n{actions}'
                guidance_trajectories.append(example)
        return "\n\n".join(guidance_trajectories)


if __name__ == "__main__":
    trajectory_manager = TrajectoryManager(base_path="./trace_data")
    experience_table = ExperienceTable(trajectory_manager)
    experience_table.add_single_experience("search_player_trace")
    query = "search a single-flight ticket from Shanghai to Beijing on April 20th."
    guidance = experience_table.query_experience(query)
    print("Guidance Trajectories:\n", guidance)


            