"""Console Frontend -- Interactive terminal interface for HC Agent."""
from __future__ import annotations
import sys, os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hc_agent import HCAgent

# ANSI color codes
C_RESET  = "\033[0m"
C_CYAN   = "\033[96m"
C_GREEN  = "\033[92m"
C_YELLOW = "\033[93m"
C_RED    = "\033[91m"
C_MAGENTA= "\033[95m"
C_DIM    = "\033[2m"
C_BOLD   = "\033[1m"


class ConsoleFrontend:
    """Rich terminal frontend for interacting with HC Agent."""

    def __init__(self, agent: "HCAgent"):
        self.agent = agent
        self.running = False

    def start(self):
        self.running = True
        self._print_banner()
        while self.running:
            try:
                user_input = input(f"\n{C_CYAN}You > {C_RESET}").strip()
                if not user_input:
                    continue
                cmd = user_input.lower()
                if cmd in ("exit", "quit", "q"):
                    self._print_goodbye()
                    break
                if cmd == "status":
                    self._print_status(); continue
                if cmd == "memory":
                    self._print_memory(); continue
                if cmd == "skills":
                    self._print_skills(); continue
                if cmd == "help":
                    self._print_help(); continue

                print(f"\n{C_GREEN}HC Agent > {C_RESET}", end="", flush=True)
                full = ""
                for chunk in self.agent.chat_stream(user_input):
                    print(chunk, end="", flush=True)
                    full += chunk
                print()
            except KeyboardInterrupt:
                print(f"\n{C_YELLOW}[Interrupted]{C_RESET}"); continue
            except EOFError:
                break
            except Exception as e:
                print(f"\n{C_RED}[Error] {e}{C_RESET}")

    def _print_banner(self):
        print(f"""
{C_MAGENTA}{C_BOLD}  HC Agent v0.1{C_RESET}
{C_DIM}  CSA+HCA Hybrid Attention | CDH Budget | Paper Evolution{C_RESET}
{C_CYAN}  Type 'help' for commands, 'exit' to quit.{C_RESET}
""")

    def _print_help(self):
        print(f"""
{C_BOLD}Commands:{C_RESET}
  {C_CYAN}status{C_RESET}  -- Show agent status
  {C_CYAN}memory{C_RESET}  -- List memory items
  {C_CYAN}skills{C_RESET}  -- List skills
  {C_CYAN}help{C_RESET}    -- This help
  {C_CYAN}exit{C_RESET}    -- Quit
""")

    def _print_status(self):
        s = self.agent.get_status()
        print(f"""
{C_BOLD}=== HC Agent Status ==={C_RESET}
  Turn:     {C_YELLOW}{s['turn']}{C_RESET}
  Memory:   {C_YELLOW}{s['memory_count']}{C_RESET} items ({s['memory_total']} total)
  Budget:   {C_YELLOW}{s['budget_used']:.1%}{C_RESET} of {s['budget_total']}
  Skills:   {C_YELLOW}{s['skill_count']}{C_RESET}
  History:  {C_YELLOW}{s['history_len']}{C_RESET} messages
""")

    def _print_memory(self):
        items = self.agent.store.get_all()
        if not items:
            print(f"{C_DIM}  (empty){C_RESET}"); return
        print(f"\n{C_BOLD}=== Memory ({len(items)}) ==={C_RESET}")
        for it in items:
            age = it.age_hours()
            tag = f"[{it.tag}]" if it.tag else ""
            dom = f"({it.domain})" if it.domain else ""
            print(f"  {C_YELLOW}{it.id[:8]}{C_RESET} "
                  f"{C_MAGENTA}{tag}{C_RESET}{C_DIM}{dom}{C_RESET} "
                  f"imp={it.importance:.2f} age={age:.1f}h "
                  f"ctx={it.access_count} "
                  f"{C_DIM}{it.content[:55]}...{C_RESET}")

    def _print_skills(self):
        skills = self.agent.skills.get("skills", {})
        if not skills:
            print(f"{C_DIM}  (none){C_RESET}"); return
        print(f"\n{C_BOLD}=== Skills ({len(skills)}) ==={C_RESET}")
        for name, sk in skills.items():
            conf = sk.get("confidence", 0)
            uses = sk.get("usage_count", 0)
            bar = "=" * int(conf * 20)
            print(f"  {C_GREEN}{name}{C_RESET} "
                  f"[{bar:<20}] {conf:.2f} uses={uses}")

    def _print_goodbye(self):
        print(f"\n{C_MAGENTA}Goodbye! HC Agent session ended.{C_RESET}\n")
