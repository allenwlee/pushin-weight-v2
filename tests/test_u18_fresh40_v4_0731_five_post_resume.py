from scripts import u18_fresh40_v4_0731_five_post_resume as subject


def test_soft_array_preserves_invalid_labels_as_issues():
    issues = []
    subject.soft_array(["business_finance", "none"], subject.sol.TOPICS, {"none", "unavailable"}, "D03.audience_topics", issues)
    assert {issue["issue"] for issue in issues} == {"invalid label", "exclusive sentinel combined with another label"}


def test_soft_array_preserves_empty_array_as_issue():
    issues = []
    subject.soft_array([], subject.sol.PROMOTIONS, {"general", "none"}, "P01.post_promotions", issues)
    assert issues == [{"path": "P01.post_promotions", "issue": "empty classification array"}]
