from pydantic import BaseModel, Field


class InvestigationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class InvestigationResponse(BaseModel):
    id: int
    title: str
    description: str | None

    model_config = {"from_attributes": True}
