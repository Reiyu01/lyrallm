from typing import Dict, List, Optional, Any
from .ontology_generator import GenerationResult
from .objects import OntologyObject

class OntologyStore:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OntologyStore, cls).__new__(cls)
            cls._instance.ontologies = {}  # type: Dict[str, GenerationResult]
        return cls._instance

    def save_ontology(self, result: GenerationResult):
        self.ontologies[result.ontology_id] = result

    def get_ontology(self, ontology_id: str) -> Optional[GenerationResult]:
        return self.ontologies.get(ontology_id)

    def get_all_ontologies(self) -> List[GenerationResult]:
        return list(self.ontologies.values())
    
    def get_all_objects(self) -> List[OntologyObject]:
        all_objects = []
        for ontology in self.ontologies.values():
            all_objects.extend(ontology.objects)
        return all_objects

    def get_stats(self) -> Dict[str, Any]:
        total_objects = sum(len(o.objects) for o in self.ontologies.values())
        total_relationships = sum(len(o.relationships) for o in self.ontologies.values())
        
        # Count by type
        type_counts = {}
        for obj in self.get_all_objects():
            obj_type = obj.object_type.value if hasattr(obj.object_type, 'value') else str(obj.object_type)
            type_counts[obj_type] = type_counts.get(obj_type, 0) + 1
            
        return {
            "total_ontologies": len(self.ontologies),
            "total_objects": total_objects,
            "total_relationships": total_relationships,
            "object_counts_by_type": type_counts
        }

# Global instance
ontology_store = OntologyStore()
