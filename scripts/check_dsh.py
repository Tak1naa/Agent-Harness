"""No model prompt is sent; validate the SDK runtime and MCP startup only."""
import json
from pathlib import Path
from deepseek_harness import DeepSeekHarness
root=Path(__file__).resolve().parents[1]
patch=root/'.dsh'/'safety.patch.yml';patch.parent.mkdir(exist_ok=True)
patch.write_text('''- insert:
    - id: bjtu-safety-tools
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: safety
        transport: stdio
        command: '''+json.dumps(str(root/'.venv/bin/python'))+'''
        args: ['-m', 'safety_harness.mcp_server']
        toolCallTimeoutMs: 120000
        failOnStartupError: true
''')
try:
 with DeepSeekHarness(cwd=str(root),runtime_cwd=str(root),dsh_home=str(root/'.dsh'),patches=(str(patch),),env={'DEEPSEEK_API_KEY':'','HARNESS_WORKSPACE':str(root)},initialize_timeout_seconds=30) as h:
  result={'status':'initialized','sdk':'0.2.1rc2','mcp_startup_fail_closed':True,'model_turn':'not_run','api_requests':0}
except Exception as e:
 result={'status':'blocked','exception':type(e).__name__,'reason':str(e),'model_turn':'not_run','api_requests':0}
(root/'results'/'dsh-integration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
