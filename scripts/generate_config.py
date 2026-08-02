#!/usr/bin/env python3
"""
Sovereign Swarm — Configuration Generator
Generates custom pre_process.py, SOUL.md, AGENTS.md, and skill.yaml
from Jinja2-style templates based on user's domains and preferences.

Called by configure.sh with environment variables set.
"""
import json
import os
import sys
from datetime import date


def load_template(path):
    """Load a .j2 template file."""
    with open(path) as f:
        return f.read()


def replace_placeholders(template, replacements):
    """Replace {{VARIABLE}} placeholders in template."""
    result = template
    for key, val in replacements.items():
        result = result.replace(key, str(val))
    return result


def generate_pre_process(template_path, output_path, domains, keywords_dict):
    """Generate pre_process.py with custom INTENT_KEYWORDS."""
    template = load_template(template_path)

    # Build INTENT_KEYWORDS dict
    keyword_lines = "INTENT_KEYWORDS = {\n"
    for domain in domains:
        kws = [k.strip() for k in keywords_dict[domain].split(",") if k.strip()]
        keyword_lines += f'    "{domain}": [\n'
        for kw in kws:
            keyword_lines += f'        "{kw}",\n'
        keyword_lines += "    ],\n"
    keyword_lines += "}\n"

    # Build valid_domains list for output validation
    valid_domains = [f'"{d}"' for d in domains] + ['"general"']
    valid_domains_str = "[" + ", ".join(valid_domains) + "]"

    # Replace placeholders
    output = template.replace("{{INTENT_KEYWORDS}}", keyword_lines)
    output = output.replace("{{VALID_DOMAINS}}", valid_domains_str)

    with open(output_path, 'w') as f:
        f.write(output)
    print(f"  ✅ {os.path.basename(output_path)} generated")


def generate_soul(template_path, output_path, domains, descriptions, distill_model, reasoning_model):
    """Generate SOUL.md with custom domains."""
    template = load_template(template_path)

    domain_list = ", ".join(domains)

    # Domain boundaries
    boundaries = ""
    for d in domains:
        desc = descriptions.get(d, d)
        boundaries += f"- **{d}**: {desc}\n"

    # Profiles
    profiles = ""
    for d in domains:
        profiles += f"- **{d}** — {d}-specific work\n"

    replacements = {
        "{{DATE}}": date.today().isoformat(),
        "{{DOMAIN_LIST}}": domain_list,
        "{{DISTILL_MODEL}}": distill_model,
        "{{REASONING_MODEL}}": reasoning_model,
        "{{DOMAIN_BOUNDARIES}}": boundaries,
        "{{PROFILES}}": profiles,
    }

    output = replace_placeholders(template, replacements)

    with open(output_path, 'w') as f:
        f.write(output)
    print(f"  ✅ {os.path.basename(output_path)} generated")


def generate_agents(template_path, output_path, user_description, use_case, domains, distill_model, reasoning_model):
    """Generate AGENTS.md with user profile."""
    template = load_template(template_path)

    domain_list = ", ".join(domains)

    replacements = {
        "{{DATE}}": date.today().isoformat(),
        "{{USER_DESCRIPTION}}": user_description,
        "{{USE_CASE}}": use_case,
        "{{DISTILL_MODEL}}": distill_model,
        "{{REASONING_MODEL}}": reasoning_model,
        "{{DOMAIN_LIST}}": domain_list,
    }

    output = replace_placeholders(template, replacements)

    with open(output_path, 'w') as f:
        f.write(output)
    print(f"  ✅ {os.path.basename(output_path)} generated")


def generate_skill_yaml(template_path, output_path, domains, descriptions, distill_model, reasoning_model):
    """Generate skill.yaml with custom specialists."""
    template = load_template(template_path)

    domain_list = ", ".join(domains)

    # Build specialists list
    specialists = ""
    for d in domains:
        desc = descriptions.get(d, d)
        specialists += f"  - {d}: {desc}\n"
    specialists += "  - general: Fallback for unclassified"

    replacements = {
        "{{DISTILL_MODEL}}": distill_model,
        "{{REASONING_MODEL}}": reasoning_model,
        "{{DOMAIN_LIST}}": domain_list,
        "{{SPECIALISTS}}": specialists,
    }

    output = replace_placeholders(template, replacements)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(output)
    print(f"  ✅ {os.path.basename(output_path)} generated")


def main():
    """Read config from environment variables and generate all files."""
    # ── Read config from environment ──
    templates_dir = os.environ.get("TEMPLATES_DIR", "templates")
    scripts_dir = os.environ.get("SCRIPTS_DIR", os.path.expanduser("~/.hermes/scripts"))
    soul_path = os.environ.get("SOUL_PATH", os.path.expanduser("~/.hermes/SOUL.md"))
    agents_path = os.environ.get("AGENTS_PATH", os.path.expanduser("~/.hermes/AGENTS.md"))
    skill_path = os.environ.get("SKILL_PATH", os.path.expanduser("~/.hermes/skills/sovereign-swarm/skill.yaml"))

    domains_json = os.environ.get("DOMAINS_JSON", '["legal","finance","systems","solar","stochastic","interpersonal"]')
    keywords_json = os.environ.get("KEYWORDS_JSON", '{}')
    descriptions_json = os.environ.get("DESCRIPTIONS_JSON", '{}')

    user_description = os.environ.get("USER_DESCRIPTION", "a user of the Sovereign Swarm")
    use_case = os.environ.get("USE_CASE", "general assistance")
    distill_model = os.environ.get("DISTILL_MODEL", "gemma4:31b-cloud")
    reasoning_model = os.environ.get("REASONING_MODEL", "deepseek-v4-flash:cloud")

    # Parse JSON
    domains = json.loads(domains_json)
    keywords_dict = json.loads(keywords_json)
    descriptions_dict = json.loads(descriptions_json)

    # Ensure all domains have entries
    for d in domains:
        if d not in keywords_dict:
            keywords_dict[d] = d
        if d not in descriptions_dict:
            descriptions_dict[d] = d

    # ── Generate files ──
    print("Generating configuration files from templates...")

    generate_pre_process(
        os.path.join(templates_dir, "pre_process.py.j2"),
        os.path.join(scripts_dir, "pre_process.py"),
        domains, keywords_dict
    )

    generate_soul(
        os.path.join(templates_dir, "SOUL.md.j2"),
        soul_path,
        domains, descriptions_dict, distill_model, reasoning_model
    )

    generate_agents(
        os.path.join(templates_dir, "AGENTS.md.j2"),
        agents_path,
        user_description, use_case, domains, distill_model, reasoning_model
    )

    generate_skill_yaml(
        os.path.join(templates_dir, "skill.yaml.j2"),
        skill_path,
        domains, descriptions_dict, distill_model, reasoning_model
    )

    print("All configuration files generated successfully.")


if __name__ == "__main__":
    main()
