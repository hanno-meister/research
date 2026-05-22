from pathlib import Path

from pydantic import BaseModel, SecretStr

try:
  from config import config
except ModuleNotFoundError:
  import sys
  from pathlib import Path

  sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
  from config import config

class LangGraphConfig(BaseModel):
  small_model: str = config.small_model
  large_model: str = config.large_model
  openai_base_url: str = config.openai_base_url
  azure_openai_api_key: SecretStr = config.azure_openai_api_key
  exa_api_key: SecretStr | None = config.exa_api_key
  tavily_api_key: SecretStr | None = config.tavily_api_key
  max_research_iterations: int = 3
  evidence_root: Path | None = None
