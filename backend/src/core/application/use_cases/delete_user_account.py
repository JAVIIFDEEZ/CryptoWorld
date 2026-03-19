from typing import Dict, Any
from core.domain.repositories.user_repository import IUserRepository

class DeleteUserAccountUseCase:
    def __init__(self, user_repository: IUserRepository):
        self.user_repository = user_repository

    def execute(self, user_id: int) -> Dict[str, Any]:
        user = self.user_repository.get_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        self.user_repository.delete(user_id)
        return {"success": True}
