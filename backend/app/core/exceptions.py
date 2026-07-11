"""Custom exception classes for business logic."""


class BusinessError(Exception):
    """Base business exception."""
    
    def __init__(self, message: str, code: str = "BUSINESS_ERROR", status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


class ValidationError(BusinessError):
    """Validation failed."""
    
    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(message, code, 422)


class NotFoundError(BusinessError):
    """Resource not found."""
    
    def __init__(self, message: str = "Resource not found", code: str = "NOT_FOUND"):
        super().__init__(message, code, 404)


class DatabaseError(BusinessError):
    """Database operation failed."""
    
    def __init__(self, message: str = "Database error", code: str = "DB_ERROR"):
        super().__init__(message, code, 500)


class FileProcessingError(BusinessError):
    """File upload/processing failed."""
    
    def __init__(self, message: str, code: str = "FILE_ERROR"):
        super().__init__(message, code, 400)
