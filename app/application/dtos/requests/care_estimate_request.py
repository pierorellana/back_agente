from pydantic import BaseModel, Field


class CareEstimateRequest(BaseModel):
    document_number: str = Field(
        min_length=1,
        description="Cedula, user_id o member_id del paciente.",
    )
    symptom_text: str = Field(
        min_length=5,
        description="Descripcion libre del sintoma escrita por el paciente.",
    )
