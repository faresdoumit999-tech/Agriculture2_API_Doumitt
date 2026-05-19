# exceptions.py

class DoumittBaseException(Exception):
    """الأساس (الأب) الذي سترث منه كل أخطاء المشروع"""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


class UserAlreadyExistsError(DoumittBaseException):
    """خطأ مخصص: عند محاولة التسجيل باسم مستخدم موجود مسبقاً"""
    def __init__(self, username: str):
        super().__init__(
            message=f"عذراً، اسم المستخدم '{username}' محجوز مسبقاً. الرجاء اختيار اسم آخر.",
            status_code=400
        )


class InvoiceNotFoundError(DoumittBaseException):
    """خطأ مخصص: عند طلب فاتورة غير موجودة"""
    def __init__(self, invoice_id: int):
        super().__init__(
            message=f"عذراً، الفاتورة رقم {invoice_id} غير موجودة في النظام.",
            status_code=404
        )