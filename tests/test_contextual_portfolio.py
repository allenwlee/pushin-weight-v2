"""Observed identity collisions must not become tracked-model brands."""
from pathlib import Path

import pytest

from x_monitor.attribution import (
    compile_keyword_index,
    detect_brand_mentions,
    matches_brand_exclusion,
)
from x_monitor.harvest_policy import load_policy

POLICY = Path(__file__).resolve().parents[1] / 'config/harvest_policy.yaml'


@pytest.mark.parametrize('text,excluded', [
    ('Meta Muse AI invitation https://t.co/rdYf1ZLPQN', False),
    ('Kimi is a role model in F1', True),
    ('Kimi and Hamilton are model drivers', True),
])
def test_brand_exclusions_preserve_racing_bans_without_url_fragment_matches(text, excluded):
    assert matches_brand_exclusion(text, ('f1', 'hamil')) is excluded


LEGACY = {
    'inclusionai': ['inclusion', 'InclusionAI', 'Ling', 'Ring', 'Ming', 'ring-1t', 'ling-flash'],
    'yi': ['Yi', '01.AI', 'Yi LLM', 'Yi-Large', 'Yi-Coder'],
    'mimo': ['MiMo', 'Xiaomi MiMo', '小米', 'MiMo-V2.5'],
    'moonshot_kimi': ['Kimi', 'Moonshot', 'K2', 'K3', '暗面', 'Moonshot AI', 'Kimi Code'],
    'nemo_megatron': ['NeMo', 'NVIDIA', 'Megatron', 'Canary', 'Drive', 'Clara', 'TAO', 'Nemotron', 'DLSS', 'Omniverse', 'Parakeet'],
}


def index():
    return compile_keyword_index(
        [(b, t, False) for b, terms in LEGACY.items() for t in terms],
        policy=load_policy(POLICY),
    )


@pytest.mark.parametrize('brand,text', [
    ('inclusionai', 'A robot at a wedding delivered the ring. Clara researches humanoid robotics.'),
    ('inclusionai', 'Alarm bells about AI and robots ring louder each day.'),
    ('inclusionai', 'Giving LLMs molecular data is useful for inclusion of new research.'),
    ('yi', 'Quantum Mpemba effect in the Dicke model. Yi Qin is an author.'),
    ('yi', '@YiChiaChentw @arcprize congratulations Yi-Chia, amazing AI work!'),
    ('mimo', 'Mimo wszystko kupujemy dalej bitcoin.'),
    ('mimo', 'Xiaomi is releasing another phone model this year.'),
    ('moonshot_kimi', 'Kimi Antonelli is a true role model for young F1 drivers.'),
    ('moonshot_kimi', 'An AI prediction says Max wins five races and Kimi wins two.'),
    ('moonshot_kimi', 'The K2 winter documentary is excellent.'),
    ('nemo_megatron', 'Clara works at OpenMind on frontier robotics.'),
    ('nemo_megatron', 'AI investments drive cost control at Google.'),
    ('nemo_megatron', 'Canary Capital has launched a crypto ETF.'),
    ('nemo_megatron', 'The TAO token funds a decentralized AI network.'),
    ('nemo_megatron', 'Finding Nemo is a great animated film.'),
    ('nemo_megatron', 'DLSS improves game rendering.'),
    ('nemo_megatron', 'I prefer the Omniverse cartoon.'),
    ('nemo_megatron', 'NVIDIA AI stocks plunged.'),
])
def test_observed_wrong_meanings_are_not_brand_evidence(brand, text):
    assert brand not in detect_brand_mentions(text, index())


@pytest.mark.parametrize('brand,text', [
    ('inclusionai', 'InclusionAI releases its latest model.'),
    ('inclusionai', 'Ring-1T open weights are available for local LLM inference.'),
    ('inclusionai', 'Ling-flash inference API supports the new weights.'),
    ('yi', 'Yi-Large is an open language model for local inference.'),
    ('yi', 'Yi-Coder released its new weights.'),
    ('mimo', 'MiMo-V2.5 benchmark results and new model weights.'),
    ('mimo', '小米大模型研究更新。'),
    ('moonshot_kimi', 'Kimi K3.1 Pro opens model weights for inference.'),
    ('moonshot_kimi', 'Moonshot AI released Hosted Agents.'),
    ('nemo_megatron', 'Nemotron open weights support long-context inference.'),
    ('nemo_megatron', 'Parakeet ASR runs locally for speech recognition.'),
    ('nemo_megatron', 'NVIDIA DRIVE uses CUDA for autonomous vehicle inference.'),
    ('nemo_megatron', 'NVIDIA Omniverse simulation tools.'),
])
def test_identified_model_and_product_controls_remain(brand, text):
    assert brand in detect_brand_mentions(text, index())
