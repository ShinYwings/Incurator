"""
Demo: MCP multi-turn conversation → Exhibition accumulation → wiki promotion.

Shows:
  Turn 1  — agent reads initial Exhibition, asks about 2DGS surface extraction
  Turn 2  — agent asks follow-up about EWA anti-aliasing → Exhibition updated
  Turn 3  — agent adds a concrete implementation insight → Exhibition updated
  Final   — promote to 02_Wiki/

Run:
    python scripts/dev/GS_Testbed/demo_mcp_conversation.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import textwrap
from pathlib import Path

import yaml
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


ROOT = Path(__file__).resolve().parents[4] / "testbed"
WORKSPACE = ROOT / "01_Workspaces" / "Gaussian Splatting Geometry Lab"
EXH_DIR = ROOT / ".curator" / "Collections" / "04_Exhibitions"

SEP = "─" * 72


def _data(result):
    if hasattr(result, "content") and result.content:
        return json.loads(result.content[0].text)
    return result


def _preview(text: str, lines: int = 6) -> str:
    stripped = text.strip()
    all_lines = stripped.splitlines()
    head = "\n".join(all_lines[:lines])
    tail = f"\n  … ({len(all_lines) - lines} more lines)" if len(all_lines) > lines else ""
    return textwrap.indent(head + tail, "  ")


def _show_exh(label: str, exh_id: str) -> None:
    path = EXH_DIR / f"{exh_id}.md"
    if not path.exists():
        print(f"  [{label}] ⚠  {exh_id}.md not found")
        return
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
    body_lines = (parts[2] if len(parts) >= 3 else text).strip().splitlines()
    sections = [l for l in body_lines if l.startswith("- **")]
    n_followups = sum(1 for l in body_lines if l.startswith("## Follow-up:"))
    print(f"\n{SEP}")
    print(f"  [{label}] {exh_id}.md")
    print(f"  core_concepts : {len(fm.get('core_concepts', []))} entries")
    print(f"  confidence    : {fm.get('confidence_score', '?')}")
    print(f"  last_updated  : {fm.get('last_updated', '?')}")
    print(f"  sections      : {len(sections)} top-level  |  follow-ups: {n_followups}")
    print(f"  body preview  :")
    print(_preview("\n".join(body_lines)))
    print(SEP)


async def run_demo() -> None:
    if not ROOT.exists():
        raise SystemExit("testbed/ not found — run: wiki testbed init GS_Testbed --force")
    if not (WORKSPACE / "curate.yml").exists():
        raise SystemExit("curate.yml missing in workspace")

    env = os.environ.copy()
    env["WIKI_ROOT"] = str(ROOT)
    env["WORKSPACE_PATH"] = str(WORKSPACE)

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "curator.cli", "mcp"],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # ── 0. 초기 상태 확인 ──────────────────────────────────────────
            print(f"\n{'═'*72}")
            print("  STEP 0 — 초기 상태 확인")
            print(f"{'═'*72}")
            layers = _data(await session.call_tool("curator_layer_index", arguments={}))
            exh_count = layers["layers"]["exhibition"]["count"]
            samples = layers["layers"]["exhibition"]["samples"]
            print(f"  exhibitions : {exh_count}개")
            if not samples:
                raise SystemExit("Exhibition이 없습니다. wiki curate --workspace 를 먼저 실행하세요.")
            exh_id = samples[0]
            print(f"  workspace Exhibition : {exh_id}")
            _show_exh("초기", exh_id)

            # ── 1. Turn 1 — 2DGS 표면 추출 질의 ───────────────────────────
            print(f"\n{'═'*72}")
            print("  TURN 1 — Agent가 2DGS 표면 재구성에 대해 질의")
            print(f"{'═'*72}")
            q1 = "2D Gaussian Splatting에서 표면 재구성은 어떻게 이루어지나요?"
            search1 = _data(await session.call_tool(
                "search_curator",
                arguments={"query": q1, "limit": 4},
            ))
            print(f"  검색어    : {q1!r}")
            print(f"  hits      : {search1.get('count', 0)}개  |  curate_spec_applied: {search1.get('curate_spec_applied')}")
            for h in search1.get("hits", [])[:3]:
                print(f"    • [{h['score']:.2f}] {h['path']}")

            # Agent가 Exhibition에 첫 번째 인사이트를 기록
            node1 = _data(await session.call_tool(
                "curator_get_node", arguments={"node_id": exh_id}
            ))
            updated_body = node1["body"].rstrip() + textwrap.dedent("""

                ## Agent Session Notes — Turn 1

                **2DGS Surface Extraction**: 2D Gaussian primitives (surfels) are
                constrained to planar disks with explicit ray–splat intersection.
                Depth distortion loss (𝓛_dist) and normal consistency loss (𝓛_normal)
                enforce surface thinness, enabling direct TSDF mesh extraction without
                post-processing. Key distinction from 3DGS: perspective-correct geometry
                is maintained by construction rather than regularization heuristics.
            """)
            fm1 = node1["frontmatter"].copy()
            updated_content1 = f"---\n{yaml.safe_dump(fm1, sort_keys=False)}---\n{updated_body}\n"
            r1 = _data(await session.call_tool(
                "curator_update_node",
                arguments={"node_id": exh_id, "new_content": updated_content1},
            ))
            print(f"\n  curator_update_node → updated={r1.get('updated')}  routing_rebuilt={r1.get('routing_tables_rebuilt')}  gaps={len(r1.get('gaps', []))}")
            _show_exh("Turn 1 후", exh_id)

            # ── 2. Turn 2 — EWA 안티앨리어싱 심층 질의 ───────────────────
            print(f"\n{'═'*72}")
            print("  TURN 2 — Agent가 EWA 안티앨리어싱 수학적 기반을 질의")
            print(f"{'═'*72}")
            q2 = "EWA splatting에서 projective Jacobian과 antialiasing 필터의 관계는?"
            search2 = _data(await session.call_tool(
                "search_curator",
                arguments={"query": q2, "limit": 4},
            ))
            print(f"  검색어    : {q2!r}")
            print(f"  hits      : {search2.get('count', 0)}개")
            for h in search2.get("hits", [])[:3]:
                print(f"    • [{h['score']:.2f}] {h['path']}")

            node2 = _data(await session.call_tool(
                "curator_get_node", arguments={"node_id": exh_id}
            ))
            updated_body2 = node2["body"].rstrip() + textwrap.dedent("""

                ## Agent Session Notes — Turn 2

                **EWA Jacobian → Antialiasing**: The projective Jacobian J_k linearises
                the perspective mapping φ locally at each surfel. Screen-space covariance
                Σ' = J Σ J^T determines the EWA footprint filter. Convolving with a
                Gaussian low-pass h prevents aliasing during rasterisation. Practical
                implication: anisotropic footprints require per-splat Jacobian evaluation;
                a shared global approximation degrades quality at extreme foreshortening.
            """)
            fm2 = node2["frontmatter"].copy()
            updated_content2 = f"---\n{yaml.safe_dump(fm2, sort_keys=False)}---\n{updated_body2}\n"
            r2 = _data(await session.call_tool(
                "curator_update_node",
                arguments={"node_id": exh_id, "new_content": updated_content2},
            ))
            print(f"\n  curator_update_node → updated={r2.get('updated')}  gaps={len(r2.get('gaps', []))}")
            _show_exh("Turn 2 후", exh_id)

            # ── 3. Turn 3 — 구현 인사이트 합성 ────────────────────────────
            print(f"\n{'═'*72}")
            print("  TURN 3 — Agent가 구현 인사이트를 합성하여 기록")
            print(f"{'═'*72}")

            node3 = _data(await session.call_tool(
                "curator_get_node", arguments={"node_id": exh_id}
            ))
            updated_body3 = node3["body"].rstrip() + textwrap.dedent("""

                ## Agent Session Notes — Turn 3 (Synthesis)

                **Unified Implementation Checklist** (derived from Turns 1–2):
                1. Replace 3DGS volumetric primitives with 2DGS planar surfels
                   (use `s_u`, `s_v` scale + `t_u`, `t_v` tangent frame).
                2. Add per-ray depth distortion loss 𝓛_dist in training loop.
                3. Add normal consistency loss 𝓛_normal = ‖N_rendered − ∇D_rendered‖₁.
                4. Implement per-splat Jacobian J_k = ∂φ/∂t_k for EWA footprint.
                5. Convolve screen-space covariance Σ' = JΣJ^T with Gaussian low-pass h.
                6. Export mesh via TSDF marching cubes — no post-processing needed.

                **Confidence assessment**: Implementation items 1–3 are well-evidenced
                by ATM-level claims. Items 4–5 require EWA paper validation before
                deployment. Mark items 4–5 as needs_review pending real-model
                verification run.
            """)
            fm3 = node3["frontmatter"].copy()
            updated_content3 = f"---\n{yaml.safe_dump(fm3, sort_keys=False)}---\n{updated_body3}\n"
            r3 = _data(await session.call_tool(
                "curator_update_node",
                arguments={"node_id": exh_id, "new_content": updated_content3},
            ))
            print(f"\n  curator_update_node → updated={r3.get('updated')}  gaps={len(r3.get('gaps', []))}")
            _show_exh("Turn 3 후 (최종 Exhibition 상태)", exh_id)

            # ── 4. wiki 승격 ────────────────────────────────────────────────
            print(f"\n{'═'*72}")
            print("  STEP 4 — Exhibition을 02_Wiki/로 승격")
            print(f"{'═'*72}")

            # Read final Exhibition
            final_path = EXH_DIR / f"{exh_id}.md"
            final_text = final_path.read_text(encoding="utf-8")
            parts = final_text.split("---", 2)
            final_body = parts[2].strip() if len(parts) >= 3 else final_text

            # Write to 02_Wiki/
            wiki_dir = ROOT / "02_Wiki" / "Gaussian Splatting"
            wiki_dir.mkdir(parents=True, exist_ok=True)
            wiki_slug = "2DGS-EWA-Implementation-Guide.md"
            wiki_path = wiki_dir / wiki_slug

            promoted_content = f"""---
title: "2DGS + EWA Implementation Guide"
source_exhibition: "[[04_Exhibitions/{exh_id}]]"
promoted_by: agent
promoted_date: 2026-05-08
tags: [gaussian-splatting, 2DGS, EWA, implementation]
---

{final_body}
"""
            wiki_path.write_text(promoted_content, encoding="utf-8")
            print(f"  ✓ 승격 완료: 02_Wiki/Gaussian Splatting/{wiki_slug}")
            print(f"  파일 크기 : {wiki_path.stat().st_size:,} bytes")

            # Verify final state
            final_layers = _data(await session.call_tool("curator_layer_index", arguments={}))
            print(f"\n  최종 레이어 상태:")
            for layer, info in final_layers["layers"].items():
                print(f"    {layer:12s}: {info['count']}개")

    print(f"\n{'═'*72}")
    print("  데모 완료")
    print(f"    workspace Exhibition : {exh_id}")
    print(f"    wiki 승격 파일       : 02_Wiki/Gaussian Splatting/{wiki_slug}")
    print(f"{'═'*72}\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
