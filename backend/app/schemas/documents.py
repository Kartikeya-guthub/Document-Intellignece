from pydantic import BaseModel, Field
from typing import List, Optional

class LineItem(BaseModel):
    item: Optional[str] = None
    qty: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None

class InvoiceSchema(BaseModel):
    """Locked Schema for Invoice (Degraded / Photographed Sample)"""
    seller: Optional[str] = None
    buyer: Optional[str] = None
    invoice_no: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    line_items: List[LineItem] = Field(default_factory=list)

class SalarySlipSchema(BaseModel):
    """Locked Schema for Salary Slip (Clean Sample)"""
    employee_name: Optional[str] = None
    employer: Optional[str] = None
    pay_period: Optional[str] = None
    gross: Optional[float] = None
    deductions: Optional[float] = None
    net_pay: Optional[float] = None
