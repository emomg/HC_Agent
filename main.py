"""HC Agent -- Main entry point.

Usage:
    HC_Agent gateway                  # Streamlit web frontend (recommended)
    HC_Agent console                  # Interactive terminal
    HC_Agent task "do X"              # Single task mode
    HC_Agent evolve                   # Paper evolution cycle
    HC_Agent reflect                  # Reflection cycle
    HC_Agent explore                  # Autonomous exploration
    HC_Agent failures                 # Failure pattern report
"""
from __future__ import annotations
import argparse, sys, os, json

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import HCConfig as Config
from hc_agent import HCAgent
from frontends.console import ConsoleFrontend

# Subcommand aliases -> normalized mode
_SUBCMD_MAP = {
    "gateway": "streamlit",
    "console": "console",
    "task": "task",
    "evolve": "evolve",
    "reflect": "reflect",
    "meta-reflect": "meta_reflect",
    "explore": "explore",
    "failures": "failures",
}


def _parse_args():
    """Parse subcommand or legacy --flag style."""
    # Detect subcommand style: HC_Agent <cmd> [args...]
    if len(sys.argv) >= 2 and sys.argv[1] in _SUBCMD_MAP:
        cmd = sys.argv[1]
        mode = _SUBCMD_MAP[cmd]
        rest = sys.argv[2:]
        # Build an argparse Namespace manually
        ns = argparse.Namespace(
            task=None, evolve=False, reflection=False, meta_reflect=False,
            streamlit=False, failures=False, explore=False,
            topic="AI agent architectures", config=None, port=0,
        )
        if mode == "streamlit":
            ns.streamlit = True
        elif mode == "task":
            ns.task = " ".join(rest) if rest else ""
        elif mode == "evolve":
            ns.evolve = True
            if rest:
                ns.topic = " ".join(rest)
        elif mode == "reflect":
            ns.reflection = True
        elif mode == "meta_reflect":
            ns.meta_reflect = True
        elif mode == "failures":
            ns.failures = True
        elif mode == "explore":
            ns.explore = True
            if rest:
                ns.topic = " ".join(rest)
        return ns

    # Legacy --flag style
    parser = argparse.ArgumentParser(description="HC Agent")
    parser.add_argument("--task", type=str, help="Run a single task and exit")
    parser.add_argument("--evolve", action="store_true", help="Run paper evolution cycle")
    parser.add_argument("--reflection", action="store_true", help="Run reflection cycle")
    parser.add_argument("--meta-reflect", action="store_true", help="Run meta-reflection on evolution effectiveness")
    parser.add_argument("--streamlit", action="store_true", help="Launch Streamlit web frontend")
    parser.add_argument("--failures", action="store_true", help="Show failure pattern report")
    parser.add_argument("--explore", action="store_true", help="Run autonomous exploration")
    parser.add_argument("--topic", type=str, default="AI agent architectures", help="Topic for evolution/exploration")
    parser.add_argument("--config", type=str, help="Path to config JSON")
    parser.add_argument("--port", type=int, default=0, help="Web server port (future)")
    return parser.parse_args()


def main():
    args = _parse_args()

    # Load config
    cfg = Config()
    if args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            overrides = json.load(f)
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
    cfg.ensure_dirs()

    # -- Streamlit frontend (launch directly, stapp.py handles its own HCAgent init) --
    if args.streamlit:
        import subprocess
        stapp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontends", "stapp.py")
        port = 8501
        print(f"[HC Agent] Starting Streamlit on http://localhost:{port}")
        subprocess.run([sys.executable, "-m", "streamlit", "run", stapp,
                        "--server.port", str(port), "--server.headless", "true",
                        "--theme.base", "light"])
        return

    # Initialize agent
    print("[HC Agent] Initializing...")
    agent = HCAgent(cfg)

    # -- Single task mode --
    if args.task:
        print(f"[HC Agent] Task: {args.task}")
        for chunk in agent.chat_stream(args.task):
            print(chunk, end="", flush=True)
        print()
        agent.save_state()
        return

    # -- Evolution mode --
    if args.evolve:
        print(f"[HC Agent] Running evolution cycle for topic: {args.topic}")
        agent._evolve(args.topic)
        agent.save_state()
        return

    # -- Reflection mode --
    if args.reflection:
        print("[HC Agent] Running reflection...")
        report = agent.reflect()
        print(f"[HC Agent] Reflection report: {json.dumps(report, indent=2, ensure_ascii=False)}")
        agent.save_state()
        return

    # -- Meta-reflection mode --
    if args.meta_reflect:
        print("[HC Agent] Running meta-reflection...")
        report = agent.meta_reflection.analyze_effectiveness()
        print(f"[HC Agent] Meta-reflection: {json.dumps(report, indent=2, ensure_ascii=False)}")
        agent.save_state()
        return

    # -- Failure report mode --
    if args.failures:
        print("[HC Agent] Failure pattern report:")
        report = agent.failure_tracker.get_failure_report()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    # -- Autonomous exploration mode --
    if args.explore:
        print(f"[HC Agent] Autonomous exploration: {args.topic}")
        discoveries = agent.explorer.explore_topic(args.topic)
        print(f"[HC Agent] {len(discoveries)} discoveries made")
        for d in discoveries[:10]:
            print(f"  - {d.get('paper', 'N/A')}: {d.get('insight', '')[:120]}")
        agent.save_state()
        return

    # -- Interactive mode --
    console = ConsoleFrontend(agent)
    console.start()
    agent.save_state()
    print("[HC Agent] State saved. Goodbye.")


if __name__ == "__main__":
    main()
