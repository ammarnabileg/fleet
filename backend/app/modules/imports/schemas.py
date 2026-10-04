from pydantic import BaseModel


class Counts(BaseModel):
    created: int
    updated: int


class IssueOut(BaseModel):
    sheet: str
    row: int  # the row number in Excel
    code: str  # message: translations "errors.<code>" (warnings too), filled with params
    params: dict


class ImportResult(BaseModel):
    applied: bool
    vehicles: Counts
    people: Counts
    documents: int
    errors: list[IssueOut]
    warnings: list[IssueOut]
