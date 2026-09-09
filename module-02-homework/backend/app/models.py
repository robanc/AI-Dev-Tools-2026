from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


Title = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)]
Description = Annotated[str, StringConstraints(strict=True, max_length=2000)]
Status = Literal['todo', 'in_progress', 'done']


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: Title
    description: Description = ''


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    # Defaults mark omitted fields; explicit null still fails string validation.
    # Only fields in model_fields_set are applied to the stored task.
    title: Title = None
    description: Description = None
    status: Status = None


class Task(TaskCreate):
    id: Annotated[int, Field(ge=1)]
    status: Status = 'todo'
