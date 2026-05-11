from pydantic import BaseModel, SecretStr
from config import config

class LangGraphConfig(BaseModel):
  small_model: str = config.small_model
  large_model: str = config.large_model
  openai_base_url: str = config.openai_base_url
  azure_openai_api_key: SecretStr = config.azure_openai_api_key
  exa_api_key: SecretStr | None = config.exa_api_key
  tavily_api_key: SecretStr | None = config.tavily_api_key
  max_research_iterations: int = 3
