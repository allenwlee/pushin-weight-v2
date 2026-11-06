"""Local query semantics and cohort integrity, with no provider imports."""
import pytest

from scripts.harvest_db_replay import Matcher, parse, replay, searchable_content


def match(query, text, author='writer'):
    return bool(Matcher([{'call_id':'Q', 'query':query}]).calls(text, author))


def test_or_context_and_handle_are_independent():
    q='((Xiaomi OR 小米) (AI OR LLM) OR MiMo OR @XiaomiMiMo) -from:spam'
    assert match(q,'小米新AI模型')
    assert not match(q,'Xiaomi phone')
    assert match(q,'MiMo released')
    assert match(q,'@XiaomiMiMo thanks')
    assert not match(q,'@XiaomiMiMo thanks', 'spam')


def test_hyphen_words_and_exact_phrase():
    assert match('Hy5', 'Hy5-preview来了')
    assert not match('Hy5preview', 'Hy5-preview')
    assert match('Step-Audio', 'audio and step')
    assert not match('"Solar Open"', 'Open the solar panel')
    assert match('"Solar Open"', 'Solar-Open model')


def test_boundaries_preserve_cjk_without_embedded_latin_words():
    assert match('EXAONE', 'EXAONE입니다')
    assert match('MiMo', 'MiMo新版本')
    assert not match('MiMo', 'mimosa or myMiMoApp or MiMoé')
    assert match('dots.tts', 'the dots.tts inference pipeline')


def test_stored_content_is_used_without_following_links():
    post={'text':'thanks','quoted_text':'DotsOCR released',
          'entities':{'urls':[{'expanded_url':'https://github.com/NVIDIA/NeMo?utm=FakeBrand'}],
                      'user_mentions':[{'screen_name':'dotsstudioai'}]}}
    text=searchable_content(post)
    assert match('DotsOCR',text) and match('@dotsstudioai',text)
    assert match('NeMo',text) and not match('FakeBrand',text)


@pytest.mark.parametrize('query',['(Qwen OR)','(Qwen','Qwen)','list:123','lang:en'])
def test_invalid_or_unreplayable_query_is_not_silently_matched(query):
    with pytest.raises(ValueError):parse(query)


def cohort():
    return {'window_start_utc':'2026-11-04T13:00:00Z','window_end_utc':'2026-11-05T01:00:00Z',
        'snapshot_at':'2026-11-05T01:28:51Z','brands':[],
        'posts':[{'tweet_id':'1','created_at':'2026-11-04T14:00:00Z','text':'Qwen model',
                  'brand_ids':['some_other_brand'],'author_handle':'x'}]}


def test_brand_labels_define_denominator_but_never_make_a_query_match():
    queries={'queries':[{'call_id':'C3','query':'Qwen','components':['qwen']}]}
    result=replay(cohort(),queries)
    assert result['unique_caught_posts']==1
    assert next(b for b in result['brands'] if b['brand']=='some_other_brand')['caught_pct']==100
    changed=cohort();changed['posts'][0]['text']='no model name'
    changed['posts'][0]['brand_ids']=['qwen']
    assert replay(changed,queries)['unique_caught_posts']==0


@pytest.mark.parametrize('change',['duplicate','outside'])
def test_invalid_cohort_is_rejected(change):
    data=cohort()
    if change=='duplicate':data['posts'].append(data['posts'][0].copy())
    else:data['posts'][0]['created_at']='2026-11-05T01:00:00Z'
    with pytest.raises(ValueError):
        replay(data,{'queries':[{'call_id':'B1','query':'Qwen','components':['qwen']}]})


def test_chinese_and_japanese_terms_can_adjoin_latin_model_names():
    assert match('文心一言', 'Gemini文心一言山亭')
    assert match('(混元) (AI OR 模型)', '混元Hy-4对上主流模型')
    assert match('(Meta OR Muse) (トークン OR AI)', 'Museトークンを獲得')


def test_list_call_recovers_author_posts_without_double_counting_or_inactive_members():
    from scripts.harvest_db_replay import add_list_call
    data=cohort()
    data['posts'][0]['text']='No brand keyword'
    result=replay(data,{'queries':[{'call_id':'B1','query':'Qwen','components':['qwen']}]})
    manifest={'queries':[{'call_id':'A','query':'(list:42) min_faves:0 -from:spam'}]}
    membership={'snapshot_at':'now','members':[{'list_id':42,'handle':'X','active':True}]}
    updated=add_list_call(result,membership,manifest)
    assert updated['unique_caught_posts']==1
    assert updated['call_a_additional_unique_posts']==1
    assert updated['posts'][0]['matched_call_ids']==['A']
    assert result['unique_caught_posts']==0
    membership['members'][0]['active']=False
    assert add_list_call(result,membership,manifest)['unique_caught_posts']==0
    membership['members'][0].update(active=True,handle='spam')
    result['posts'][0]['author_handle']='spam'
    assert add_list_call(result,membership,manifest)['unique_caught_posts']==0


def test_circled_list_number_does_not_hide_model_name():
    assert match('(Meta OR Muse) (AI OR トークン)', '④Museが動くAIだ')
    assert not match('Muse', '4Muse')


def test_list_and_keyword_overlap_keeps_both_routes_without_double_counting():
    from scripts.harvest_db_replay import add_list_call
    data = cohort()
    result = replay(data, {'queries': [{'call_id': 'B1', 'query': 'Qwen', 'components': ['qwen']}]})
    manifest = {'queries': [{'call_id': 'A', 'query': '(list:42) min_faves:0 -from:spam'}]}
    membership = {'snapshot_at': 'now', 'members': [{'list_id': 42, 'handle': 'X', 'active': True}]}
    updated = add_list_call(result, membership, manifest)
    assert updated['unique_caught_posts'] == 1
    assert updated['call_a_additional_unique_posts'] == 0
    assert updated['posts'][0]['matched_call_ids'] == ['B1', 'A']
