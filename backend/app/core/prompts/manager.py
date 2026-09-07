from __future__ import annotations
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

class PromptManager:
    def __init__(self):
        # backend/app/core/prompts/templates
        template_path = Path(__file__).parent / "templates"
        self.env = Environment(loader=FileSystemLoader(str(template_path)))

    def render(self, template_name: str, **kwargs) -> str:
        template = self.env.get_template(template_name)
        return template.render(**kwargs)

prompt_manager = PromptManager()
