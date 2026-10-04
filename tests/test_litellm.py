import importlib.util, pathlib, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gen',ROOT/'infra/litellm/generate_config.py')
gen=importlib.util.module_from_spec(spec); spec.loader.exec_module(gen)
class LiteLLMTests(unittest.TestCase):
    def env(self):
        e={'LM_STUDIO_OPENAI_BASE_URL':'http://127.0.0.1:1234/v1','LM_STUDIO_API_KEY':'x','LOCAL_MODEL_1_ENABLED':'true','LOCAL_MODEL_1_ALIAS':'a','LOCAL_MODEL_1_CLAUDE_ALIAS':'claude-a','LOCAL_MODEL_1_MODEL_ID':'model-a','LOCAL_MODEL_2_ENABLED':'false','LOCAL_MODEL_3_ENABLED':'false','LOCAL_MODEL_4_ENABLED':'false','CLAUDE_OPUS_MODEL_NAME':'claude-opus','CLAUDE_OPUS_LOCAL_ALIAS':'a','CLAUDE_SONNET_MODEL_NAME':'claude-sonnet','CLAUDE_SONNET_LOCAL_ALIAS':'a','CLAUDE_HAIKU_MODEL_NAME':'claude-haiku','CLAUDE_HAIKU_LOCAL_ALIAS':'a','MINIMAX_ENABLED':'false','HERMES_ENABLED':'true'}
        return e
    def test_hermes_not_routed_through_litellm(self):
        cfg=gen.build_config(self.env()); names={x['model_name'] for x in cfg['model_list']}
        self.assertNotIn('hermes-tailscale-worker',names)
        self.assertIn('a',names)
