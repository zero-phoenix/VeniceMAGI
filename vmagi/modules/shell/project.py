import os


class ProjectManager:
    """
    Gestión de Proyectos Estructurados (P21.c).
    """
    def init_project(self, base_path: str) -> dict:
        """
        Inicializa un proyecto como carpeta (A21-3).
        Crea la estructura base .vmagi
        """
        magi_dir = os.path.join(base_path, ".vmagi")
        os.makedirs(magi_dir, exist_ok=True)

        # Simulamos creación del gitignore para excluir blobs grandes y el .vmagi/memory
        gitignore_path = os.path.join(base_path, ".gitignore")
        with open(gitignore_path, "w") as f:
            f.write(".vmagi/memory/\ncas/\n")

        return {"status": "created", "path": base_path}
