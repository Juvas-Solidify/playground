"""Configuration handling for the Azure DevOps Lead Finder."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_CONFIG_PATH = Path.home() / ".ado-finder" / "config.yaml"


@dataclass
class SourceConfig:
    """Configuration for a single data source."""
    enabled: bool = True
    max_results_per_query: int = 100
    delay_seconds: tuple[float, float] = (2.0, 5.0)


@dataclass
class Config:
    """Main configuration class."""
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    search_queries: list[str] = field(default_factory=list)
    regions: list[str] = field(default_factory=list)

    def __post_init__(self):
        # Set defaults if not provided
        if not self.sources:
            self.sources = {
                "linkedin": SourceConfig(
                    enabled=True,
                    max_results_per_query=100,
                    delay_seconds=(2.0, 5.0)
                ),
                "indeed": SourceConfig(
                    enabled=False,
                    max_results_per_query=100,
                    delay_seconds=(2.0, 5.0)
                ),
            }

        if not self.search_queries:
            self.search_queries = [
                "Azure DevOps",
                "Azure DevOps Engineer",
                "Azure Pipelines",
                "Azure Boards",
            ]

        if not self.regions:
            self.regions = [
                "Sweden",
                "Norway",
                "Denmark",
                "Finland",
            ]


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from a YAML file."""
    path = config_path or DEFAULT_CONFIG_PATH

    if not path.exists():
        # Return default configuration
        return Config()

    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    return _parse_config(data)


def _parse_config(data: dict[str, Any]) -> Config:
    """Parse configuration data into a Config object."""
    sources = {}
    if "sources" in data:
        for name, source_data in data["sources"].items():
            delay = source_data.get("delay_seconds", [2, 5])
            if isinstance(delay, list):
                delay = tuple(delay)
            sources[name] = SourceConfig(
                enabled=source_data.get("enabled", True),
                max_results_per_query=source_data.get("max_results_per_query", 100),
                delay_seconds=delay,
            )

    return Config(
        sources=sources,
        search_queries=data.get("search_queries", []),
        regions=data.get("regions", []),
    )


def save_config(config: Config, config_path: Optional[Path] = None) -> None:
    """Save configuration to a YAML file."""
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "sources": {
            name: {
                "enabled": source.enabled,
                "max_results_per_query": source.max_results_per_query,
                "delay_seconds": list(source.delay_seconds),
            }
            for name, source in config.sources.items()
        },
        "search_queries": config.search_queries,
        "regions": config.regions,
    }

    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def create_default_config(config_path: Optional[Path] = None) -> Config:
    """Create and save a default configuration file."""
    config = Config()
    save_config(config, config_path)
    return config


def get_source_config(config: Config, source_name: str) -> SourceConfig:
    """Get configuration for a specific source."""
    return config.sources.get(source_name, SourceConfig())
