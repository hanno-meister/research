import tomllib
from os import getenv
from pathlib import Path
from pydantic import BaseModel, SecretStr
from dotenv import load_dotenv

load_dotenv(override=True)

class Config(BaseModel):
    small_model: str
    large_model: str
    openai_base_url: str
    azure_openai_api_key: SecretStr
    exa_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None

with Path(__file__).with_name("pyproject.toml").open("rb") as f:
    pyproject = tomllib.load(f)

config = Config.model_validate({
    **pyproject["tool"]["vanguard"],
    "azure_openai_api_key": getenv("AZURE_OPENAI_API_KEY"),
    "exa_api_key": getenv("EXA_API_KEY"),
    "tavily_api_key": getenv("TAVILY_API_KEY"),
})
