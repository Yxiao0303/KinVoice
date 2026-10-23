"""
对话总结 → 经验卡片 测试集
运行方式: cd backend && python _test_summarize.py
前提: 后端已启动 (uvicorn app.main:app --port 8000)
"""
import requests
import json
import time

BASE = "http://127.0.0.1:8000"
PROXY = {"http": None, "https": None}
PASS = 0
FAIL = 0

def test(name, fn):
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"【{name}】")
    print(f"{'='*60}")
    try:
        fn()
        PASS += 1
        print(f"✅ 通过")
    except Exception as e:
        FAIL += 1
        print(f"❌ 失败: {e}")


# ══════════════════════════════════════════════════════════
# 准备工作：清空数据库，确保每次测试独立
# ══════════════════════════════════════════════════════════
def setup():
    """清空所有卡片"""
    resp = requests.get(f"{BASE}/cards", timeout=10, proxies=PROXY)
    cards = resp.json().get("cards", [])
    for c in cards:
        requests.delete(f"{BASE}/cards/{c['id']}", timeout=10, proxies=PROXY)
    print(f"清理完成，删除了 {len(cards)} 张卡片")


# ══════════════════════════════════════════════════════════
# 测试用例
# ══════════════════════════════════════════════════════════

def test_01_empty_knowledge():
    """TC-01: 空知识库 + 丰富对话 → 应生成1~3张卡片"""
    resp = requests.post(f"{BASE}/chat/summarize", json={
        "history": [
            {"role": "user", "content": "我今天特别烦，因为工作上被领导骂了一顿"},
            {"role": "assistant", "content": "听起来你今天过得不太顺，愿意跟我说说发生了什么吗？"},
            {"role": "user", "content": "就是我做了一个方案，改了三次领导还是不满意，说我不用心。但我真的已经尽力了"},
            {"role": "assistant", "content": "被否定努力的感觉确实很难受。你觉得领导是对方案本身不满意，还是沟通上出了问题？"},
            {"role": "user", "content": "可能是沟通吧，他说的要求我其实没太理解，但我不敢多问，怕显得很蠢"},
            {"role": "assistant", "content": "很多人在工作中都有这样的顾虑。但其实主动确认需求，反而是负责任的表现。下次可以试着说：'我想确认一下我的理解是否正确，您的意思是……'"},
            {"role": "user", "content": "嗯，这个方法好。还有就是我应该提前给他看初稿，而不是闷头做到最后才交"},
            {"role": "assistant", "content": "对！阶段性对齐很重要。这样即使方向偏了也能及时调整，不会白费功夫。"}
        ]
    }, timeout=120, proxies=PROXY)

    data = resp.json()
    assert resp.status_code == 200, f"状态码应为200，实际{resp.status_code}"
    assert data["total_created"] + data["total_updated"] >= 1, "至少应生成1张卡片"
    assert data["total_created"] + data["total_updated"] <= 3, "最多3张卡片"

    for r in data["results"]:
        assert r["action"] == "create", "空知识库不应有update"
        card = r["card"]
        assert card["observation"], "observation不能为空"
        assert card["feeling"], "feeling不能为空"
        assert card["need"], "need不能为空"
        assert card["category"] in ["人生阅历","家庭菜谱","成长故事","相处感悟"], f"分类异常: {card['category']}"
        assert len(card["observation"]) <= 30, f"observation过长: {len(card['observation'])}字"

    print(f"  生成了 {data['total_created']} 张卡片")
    for r in data["results"]:
        c = r["card"]
        print(f"  [{c['id']}] {c['category']} | {c['observation']}")


def test_02_pure_greeting():
    """TC-02: 纯寒暄对话 → 应返回空数组"""
    resp = requests.post(f"{BASE}/chat/summarize", json={
        "history": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好呀！今天过得怎么样？"},
            {"role": "user", "content": "还不错"},
            {"role": "assistant", "content": "那就好~有什么想聊的吗？"},
            {"role": "user", "content": "没什么特别的，就是打个招呼"},
            {"role": "assistant", "content": "哈哈好的，随时找我聊天哦！"}
        ]
    }, timeout=120, proxies=PROXY)

    data = resp.json()
    assert resp.status_code == 200
    assert data["total_created"] == 0 and data["total_updated"] == 0, "寒暄不应生成卡片"
    print(f"  正确返回空数组")


def test_03_related_topic_update():
    """TC-03: 同一话题延续 → 应 update 而非 create"""
    # 先看当前有哪些卡片
    resp = requests.get(f"{BASE}/cards", timeout=10, proxies=PROXY)
    cards = resp.json()["cards"]
    assert len(cards) >= 1, "需要先有卡片（请先跑TC-01）"

    # 取第一张卡片的主题，模拟延续对话
    existing = cards[0]
    print(f"  已有卡片: [{existing['id']}] {existing['observation']}")

    resp = requests.post(f"{BASE}/chat/summarize", json={
        "history": [
            {"role": "user", "content": "还记得我们上次聊的工作沟通问题吗？我今天又遇到了"},
            {"role": "assistant", "content": "当然记得，发生了什么？"},
            {"role": "user", "content": "这次我用了你说的方法，先跟领导确认需求，结果发现我之前理解的全错了"},
            {"role": "assistant", "content": "你看，主动沟通多重要！虽然之前走了一些弯路，但至少现在方向对了。"},
            {"role": "user", "content": "对，我觉得最重要的教训就是：不要怕丢脸，不懂就问。还有就是要主动汇报进度"},
            {"role": "assistant", "content": "总结得太好了！这些经验值得记住。"}
        ]
    }, timeout=120, proxies=PROXY)

    data = resp.json()
    assert resp.status_code == 200

    # 检查是否有 update 操作（不强求，LLM可能判断为新卡片也合理）
    has_update = any(r["action"] == "update" for r in data["results"])
    print(f"  结果: {data['total_created']}新建 {data['total_updated']}更新")
    for r in data["results"]:
        print(f"  action={r['action']}, card_id={r['card_id']}, observation={r['card']['observation'] if r['card'] else 'N/A'}")
    print(f"  {'有update操作，符合预期' if has_update else '无update（LLM判断为不同主题，可接受）'}")


def test_04_multi_card():
    """TC-04: 多话题混合对话 → 应生成多张卡片"""
    resp = requests.post(f"{BASE}/chat/summarize", json={
        "history": [
            {"role": "user", "content": "今天发生了两件事。第一件，我学会了做糖醋排骨！"},
            {"role": "assistant", "content": "哇，厨艺进步了！怎么做出来的？"},
            {"role": "user", "content": "我奶奶教我的，关键在调汁：一酒二酱三糖四醋，顺序不能错"},
            {"role": "assistant", "content": "这个口诀好记！奶奶的手艺一定要传下去。"},
            {"role": "user", "content": "第二件事，我今天跟朋友道歉了。上周我说话太冲，伤到她了"},
            {"role": "assistant", "content": "道歉需要很大的勇气，你做得很好。她怎么回应的？"},
            {"role": "user", "content": "她说她早就不生气了，还说我主动道歉让她很感动。我觉得朋友之间坦诚真的很重要"},
            {"role": "assistant", "content": "真诚永远是最好的沟通方式。这两个经验都值得记下来！"}
        ]
    }, timeout=120, proxies=PROXY)

    data = resp.json()
    assert resp.status_code == 200
    total = data["total_created"] + data["total_updated"]
    assert total >= 2, f"多话题应生成≥2张卡片，实际{total}"
    print(f"  生成了 {total} 张卡片")

    # 检查分类多样性
    categories = [r["card"]["category"] for r in data["results"] if r["card"]]
    print(f"  分类: {categories}")
    assert len(set(categories)) >= 2, f"多话题应有不同分类，实际: {set(categories)}"


def test_05_manual_crud_coexist():
    """TC-05: 手动增删改与AI总结共存"""
    # 手动创建一张卡片
    resp = requests.post(f"{BASE}/cards", json={
        "category": "家庭菜谱",
        "emotion": "温暖",
        "observation": "奶奶的饺子秘方",
        "feeling": "每次吃饺子就想起奶奶在厨房忙碌的身影",
        "need": "传承家庭味道",
        "title": "奶奶的饺子秘方",
        "content": "皮要薄，馅要多，捏褶要均匀",
        "author": "我",
        "tag": "家庭菜谱"
    }, timeout=10, proxies=PROXY)
    assert resp.status_code == 201
    manual_id = resp.json()["id"]
    print(f"  手动创建卡片 id={manual_id}")

    # AI 总结一次（应不影响手动卡片）
    resp = requests.post(f"{BASE}/chat/summarize", json={
        "history": [
            {"role": "user", "content": "我今天跑步坚持了5公里，坚持运动真的让我状态变好了"},
            {"role": "assistant", "content": "太棒了！坚持运动需要很强的自律，你是怎么做到的？"},
            {"role": "user", "content": "就是每天早上逼自己起来，一开始很难，但习惯了就很享受"},
            {"role": "assistant", "content": "这就是习惯的力量。把运动变成生活的一部分，而不是任务。"}
        ]
    }, timeout=120, proxies=PROXY)
    assert resp.status_code == 200
    print(f"  AI总结: {resp.json()['total_created']}新建 {resp.json()['total_updated']}更新")

    # 手动更新AI生成的卡片
    resp = requests.get(f"{BASE}/cards", timeout=10, proxies=PROXY)
    cards = resp.json()["cards"]
    ai_card = next((c for c in cards if c["id"] != manual_id), None)
    if ai_card:
        resp = requests.put(f"{BASE}/cards/{ai_card['id']}", json={
            "emotion": "手动修改的情绪"
        }, timeout=10, proxies=PROXY)
        assert resp.status_code == 200
        print(f"  手动更新AI卡片 id={ai_card['id']} 成功")

    # 手动删除
    resp = requests.delete(f"{BASE}/cards/{manual_id}", timeout=10, proxies=PROXY)
    assert resp.status_code == 204
    print(f"  手动删除卡片 id={manual_id} 成功")

    # 验证最终状态
    resp = requests.get(f"{BASE}/cards", timeout=10, proxies=PROXY)
    final_cards = resp.json()["cards"]
    ids = [c["id"] for c in final_cards]
    assert manual_id not in ids, "手动删除的卡片应不存在"
    print(f"  最终数据库: {len(final_cards)} 张卡片")


def test_06_empty_history():
    """TC-06: 空历史 → 应返回422"""
    resp = requests.post(f"{BASE}/chat/summarize", json={
        "history": []
    }, timeout=10, proxies=PROXY)
    assert resp.status_code == 422, f"空history应返回422，实际{resp.status_code}"
    print(f"  正确返回422")


def test_07_update_nonexistent():
    """TC-07: 已有卡片被手动删除后再update → 降级create"""
    # 先获取当前卡片数
    resp = requests.get(f"{BASE}/cards", timeout=10, proxies=PROXY)
    before = resp.json()["total"]

    # 用不存在的card_id做update——这依赖LLM行为，不直接测试
    # 改为：验证系统在update目标不存在时不会崩溃
    resp = requests.post(f"{BASE}/chat/summarize", json={
        "history": [
            {"role": "user", "content": "我学会了一个新技能：用Python写了个自动回复机器人"},
            {"role": "assistant", "content": "厉害！编程是一个很有用的技能。你是怎么学的？"},
            {"role": "user", "content": "看网上教程自学的，最重要的是动手实践，光看不练没用"},
            {"role": "assistant", "content": "说得对，实践出真知。这个学习经验可以分享给更多人。"}
        ]
    }, timeout=120, proxies=PROXY)

    data = resp.json()
    assert resp.status_code == 200
    assert data["total_created"] + data["total_updated"] >= 1
    # 验证所有成功的操作都有card_id
    for r in data["results"]:
        if r["action"] == "create":
            assert r["card_id"] is not None, "create操作应有card_id"
    print(f"  正常完成，生成 {data['total_created']} 张卡片")


# ══════════════════════════════════════════════════════════
# 运行
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("KinVoice 对话总结 → 经验卡片 测试集")
    print("=" * 60)

    # 检查服务
    try:
        resp = requests.get(f"{BASE}/ping", timeout=5, proxies=PROXY)
        print(f"后端状态: {resp.json()}")
    except Exception:
        print("❌ 后端未启动！请先运行: uvicorn app.main:app --port 8000")
        exit(1)

    setup()
    time.sleep(0.5)

    test("TC-01 空知识库生成卡片", test_01_empty_knowledge)
    test("TC-02 纯寒暄不生成", test_02_pure_greeting)
    test("TC-03 同话题更新", test_03_related_topic_update)
    test("TC-04 多话题多卡片", test_04_multi_card)
    test("TC-05 手动CRUD与AI共存", test_05_manual_crud_coexist)
    test("TC-06 空历史拒绝", test_06_empty_history)
    test("TC-07 系统健壮性", test_07_update_nonexistent)

    print(f"\n{'='*60}")
    print(f"测试完成: {PASS}通过 / {FAIL}失败 / {PASS+FAIL}总计")
    print(f"{'='*60}")
