"""Stratified weighted field-observation pivot with same-day/same-zone pairing."""
from datetime import date, timedelta
import math
import random

TEAMS = ("A队", "B队")


def metadata():
    return {
        "name": "实地调研加权透视", "short": "survey-pivot", "tagline": "把样本结构与真实覆盖结构分开，让透视结论经得起复核",
        "client": "模拟客户：南岭公共服务研究所，12名观察员分为A/B两队，复核服务点无障碍通达情况。",
        "workflow": "两支采样队按各自路线提交日表，分批收卷；同日同区域配齐后才进入加权比较，避免把出勤日况算成队伍差异。",
        "pains": ["两队中心区与外围区样本占比不同", "两队出勤日期不同，直接加权会把日况差异算成队伍差异", "先平均每日百分比扭曲总体比率", "总计方向和分层方向相反却未被提示"],
        "upstream": "实地观察日汇总、区域服务点抽样框规模", "downstream": "研究员的分层复核清单、加权结果和方法附件。",
        "entities": ["日表卷（待补齐 / 已封卷）", "同日同区域配对窗", "研究简报计划"], "dataset_name": "南岭_服务点通达_分层观察日表.csv",
        "columns": [{"key": "day", "label": "观察日", "type": "string"}, {"key": "team", "label": "采样队", "type": "string"}, {"key": "zone", "label": "区域层", "type": "string"}, {"key": "observed", "label": "观察点数", "type": "number"}, {"key": "passed", "label": "通达合格数", "type": "number"}, {"key": "frame_size", "label": "该层抽样框点数", "type": "number"}],
        "parameters": [{"key": "weight_mode", "label": "目标层权重", "type": "select", "default": "population", "options": [{"value": "population", "label": "按抽样框规模"}, {"value": "equal", "label": "各区域等权"}]}, {"key": "minimum_cell", "label": "分层最低观察量", "type": "number", "default": 50, "min": 10, "max": 500}],
        "workbench_title": "日表卷与配对加权", "action_label": "封卷并计算配对加权率", "unit": "%", "accent": "oklch(53% 0.09 215)", "style": "field-notebook",
        "seed_story": ["08:30 上传南岭_服务点通达_分层观察日表.csv，分批收日表卷。", "08:45 复核中心区抽样框6200个点、外围区3800个点。", "09:00 同日同区域配对：只有A/B两队都有记录的观察窗才进入加权。", "09:10 单边窗注明理由排除；未配齐也未排除的窗会挡住封卷。", "09:20 封卷后按配齐的窗加权，两队在各区域使用同一组日期。", "10:00 切换等权目标作敏感性比较，不能覆盖原始运行记录。", "15:00 将权重、分母和限制写入研究附件，创建本地简报分发计划。"],
        "method": "先按观察日+区域配对：同日同区域A队/B队都有记录的窗才参与计算；单边窗须注明排除理由。层内p_h=Σ合格数/Σ观察数（仅配对窗）；标准化率p=ΣW_h p_h，W_h取统一抽样框占比或等权。近似方差ΣW_h²p_h(1−p_h)/n_h；方向反转比较A−B的原始合计与每层方向。",
        "limitations": ["假设层内观察可近似独立；置信区间未处理路线聚类和有限总体修正。", "队伍比较用于说明样本构成影响，不是人员绩效排名或随机实验因果结论。", "封卷后原卷记录不再改动；迟报进入下一卷，不追溯改写已发布结论。"],
    }


def seed_records():
    rng = random.Random(1019)
    start = date(2026, 10, 1)
    result = []
    for index in range(30):
        for team, zone, size, probability, frame in (("A队", "中心区", 9, 0.95, 6200), ("A队", "外围区", 43, 0.73, 3800), ("B队", "中心区", 43, 0.89, 6200), ("B队", "外围区", 9, 0.64, 3800)):
            observed = size + rng.randint(-2, 3)
            passed = sum(rng.random() < probability for _ in range(observed))
            result.append({"day": str(start + timedelta(days=index)), "team": team, "zone": zone, "observed": observed, "passed": passed, "frame_size": frame})
    return result


def _integer(value, name, minimum):
    try:
        answer = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}必须是整数") from None
    if not math.isfinite(answer) or not answer.is_integer() or not minimum <= answer <= 1_000_000_000:
        raise ValueError(f"{name}必须是{minimum}至10亿之间的整数")
    return int(answer)


def normalize_records(records):
    """Validate and normalize day-table rows; rejects duplicates and frame conflicts."""
    if not isinstance(records, list) or not records:
        raise ValueError("请先提供区域分层观察日表")
    normalized, natural_keys, frame = [], set(), {}
    for record in records:
        try:
            day = date.fromisoformat(str(record["day"])).isoformat()
            team, zone = str(record["team"]).strip(), str(record["zone"]).strip()
            n = _integer(record["observed"], "观察点数", 1)
            passed = _integer(record["passed"], "合格数", 0)
            size = _integer(record["frame_size"], "抽样框规模", 1)
        except (KeyError, TypeError):
            raise ValueError("记录缺少日期、队伍、区域或计数字段") from None
        except ValueError as error:
            raise ValueError(str(error)) from None
        if team not in TEAMS or not zone:
            raise ValueError("队伍须为A队/B队且区域非空")
        if passed > n:
            raise ValueError("合格数不能超过观察数")
        if len(zone) > 60 or len(day) > 20:
            raise ValueError("区域或日期字段过长")
        key = (day, team, zone)
        if key in natural_keys:
            raise ValueError(f"{day} {team}/{zone} 同日同队同区域存在重复记录，请先去重")
        natural_keys.add(key)
        if zone in frame and frame[zone] != size:
            raise ValueError("同一区域的抽样框规模冲突，不能确定统一权重")
        frame[zone] = size
        normalized.append({"day": day, "team": team, "zone": zone, "observed": n, "passed": passed, "frame_size": size})
    return normalized


def _exclusion_map(exclusions):
    mapping = {}
    for item in exclusions or []:
        try:
            day = date.fromisoformat(str(item["day"])).isoformat()
            zone = str(item["zone"]).strip()
            reason = str(item.get("reason", "")).strip()
        except (KeyError, TypeError):
            raise ValueError("排除记录缺少日期、区域或理由") from None
        if not zone or len(reason) < 2:
            raise ValueError("每个排除窗必须注明至少两个字符的理由")
        if (day, zone) in mapping:
            raise ValueError("同一观察窗存在多条排除理由")
        mapping[(day, zone)] = {"day": day, "zone": zone, "reason": reason, "by": str(item.get("by", "")), "at": item.get("at")}
    return mapping


def window_report(records, exclusions=None):
    """Pair records by (day, zone). Returns paired / pending / excluded windows.

    A window is paired when both teams have a record. A window with only one
    team is pending unless it carries an explicit exclusion reason.
    """
    rows = normalize_records(records)
    reasons = _exclusion_map(exclusions)
    windows = {}
    for row in rows:
        windows.setdefault((row["day"], row["zone"]), {})[row["team"]] = row
    unknown = sorted(set(reasons) - set(windows))
    if unknown:
        day, zone = unknown[0]
        raise ValueError(f"排除记录指向不存在的观察窗：{day} {zone}")
    paired, pending, excluded = [], [], []
    for (day, zone) in sorted(windows):
        teams = windows[(day, zone)]
        present = sorted(teams)
        frame_size = next(iter(teams.values()))["frame_size"]
        if len(present) == len(TEAMS):
            if (day, zone) in reasons:
                raise ValueError(f"{day} {zone} 已配齐，不应再标注排除理由")
            paired.append({"day": day, "zone": zone, "frame_size": frame_size, "teams": present,
                           "observed": {team: teams[team]["observed"] for team in TEAMS}})
            continue
        team = present[0]
        missing = next(name for name in TEAMS if name != team)
        entry = {"day": day, "zone": zone, "frame_size": frame_size, "present_team": team, "missing_team": missing,
                 "observed": teams[team]["observed"]}
        if (day, zone) in reasons:
            entry["reason"] = reasons[(day, zone)]["reason"]
            excluded.append(entry)
        else:
            pending.append(entry)
    return {"total_windows": len(windows), "paired": paired, "pending": pending, "excluded": excluded}


def analyze(records, params):
    return analyze_volume(records, [], params)


def analyze_volume(records, exclusions, params):
    """Weighted pivot computed only over paired windows, with same dates per zone."""
    report = window_report(records, exclusions)
    if report["pending"]:
        raise ValueError(f"尚有{len(report['pending'])}个观察窗只有单边记录且未注明排除理由，不能封卷或计算")
    if not report["paired"]:
        raise ValueError("没有可用的同日同区域配对窗，无法进行加权比较")
    paired_keys = {(window["day"], window["zone"]) for window in report["paired"]}
    rows = [row for row in normalize_records(records) if (row["day"], row["zone"]) in paired_keys]

    mode = params.get("weight_mode", "population")
    if mode not in ("population", "equal"):
        raise ValueError("未知权重模式")
    minimum = _integer(params.get("minimum_cell", 50), "最低分层观察量", 10)
    if minimum > 500:
        raise ValueError("最低分层观察量不能超过500")

    cells, frame, dates = {}, {}, {}
    for row in rows:
        frame.setdefault(row["zone"], row["frame_size"])
        dates.setdefault(row["zone"], {}).setdefault(row["team"], set()).add(row["day"])
        total = cells.setdefault((row["team"], row["zone"]), {"n": 0, "passed": 0})
        total["n"] += row["observed"]
        total["passed"] += row["passed"]

    zones = sorted(frame)
    if len(zones) < 2 or any((team, zone) not in cells for team in TEAMS for zone in zones):
        raise ValueError("至少需要2个区域层，每个区域须同时有A队和B队样本")
    for zone in zones:
        if dates[zone].get(TEAMS[0], set()) != dates[zone].get(TEAMS[1], set()):
            raise ValueError(f"{zone}的A/B两队日期集合不一致，配对逻辑异常")

    frame_total = sum(frame.values())
    weights = {zone: frame[zone] / frame_total if mode == "population" else 1 / len(zones) for zone in zones}
    output, estimates, raw_rates = [], {}, {}
    warnings = []
    for team in TEAMS:
        weighted = variance = denominator = numerator = inverse_eff = 0.0
        for zone in zones:
            cell = cells[(team, zone)]
            n, passed = cell["n"], cell["passed"]
            rate = passed / n
            weight = weights[zone]
            weighted += weight * rate
            variance += weight ** 2 * rate * (1 - rate) / n
            inverse_eff += weight ** 2 / n
            numerator += passed
            denominator += n
            output.append({"team": team, "zone": zone, "passed": passed, "observed": n, "paired_days": len(dates[zone][team]),
                           "rate": round(rate*100, 3), "weight": round(weight*100, 2), "contribution": round(weight*rate*100, 3)})
            if n < minimum:
                warnings.append(f"{team}/{zone}在配对窗内仅{n}个观察点，低于最低量{minimum}。")
        se = math.sqrt(variance)
        estimates[team] = {"rate": weighted, "low": max(0, weighted-1.96*se), "high": min(1, weighted+1.96*se), "effective_n": 1/inverse_eff}
        raw_rates[team] = numerator / denominator

    for window in report["excluded"]:
        warnings.append(f"{window['zone']} {window['day']} 仅有{window['present_team']}记录，已按理由排除：{window['reason']}")

    raw_delta = raw_rates[TEAMS[0]] - raw_rates[TEAMS[1]]
    layer_deltas = [cells[(TEAMS[0], zone)]["passed"]/cells[(TEAMS[0], zone)]["n"] - cells[(TEAMS[1], zone)]["passed"]/cells[(TEAMS[1], zone)]["n"] for zone in zones]
    reversal = (raw_delta < 0 and all(delta > 0 for delta in layer_deltas)) or (raw_delta > 0 and all(delta < 0 for delta in layer_deltas))
    weighted_delta = estimates[TEAMS[0]]["rate"] - estimates[TEAMS[1]]["rate"]
    if reversal:
        warnings.append("检测到辛普森方向反转：原始合计的A−B方向与所有区域层内方向相反。")

    coverage = [{"zone": zone, "paired_days": len(dates[zone][TEAMS[0]]),
                 "days": sorted(dates[zone][TEAMS[0]]),
                 "both_teams_same_dates": dates[zone][TEAMS[0]] == dates[zone][TEAMS[1]],
                 "frame_size": frame[zone]} for zone in zones]
    day_count = len({window["day"] for window in report["paired"]})
    summary = (f"{len(report['paired'])}个同日同区域配对窗（涉及{day_count}个观察日，排除{len(report['excluded'])}个单边窗）"
               f"按{'抽样框' if mode=='population' else '区域等权'}标准化；A队加权合格率{estimates[TEAMS[0]]['rate']:.2%}，"
               f"B队{estimates[TEAMS[1]]['rate']:.2%}；{'发现' if reversal else '未发现严格的'}辛普森反转。")
    return {
        "summary": summary,
        "metrics": [{"label": "A队加权合格率", "value": round(estimates[TEAMS[0]]["rate"]*100, 3), "unit": "%"}, {"label": "B队加权合格率", "value": round(estimates[TEAMS[1]]["rate"]*100, 3), "unit": "%"}, {"label": "加权A−B", "value": round(weighted_delta*100, 3), "unit": "百分点"}, {"label": "原始A−B", "value": round(raw_delta*100, 3), "unit": "百分点"}],
        "table": {"columns": [{"key": "team", "label": "采样队"}, {"key": "zone", "label": "区域层"}, {"key": "paired_days", "label": "配对日数"}, {"key": "passed", "label": "合格分子"}, {"key": "observed", "label": "观察分母"}, {"key": "rate", "label": "层内合格率%"}, {"key": "weight", "label": "统一目标权重%"}, {"key": "contribution", "label": "加权贡献百分点"}], "rows": output},
        "chart": {"type": "bar", "labels": zones + ["原始总计", "加权总计"], "series": [{"name": team, "values": [round(cells[(team, zone)]["passed"]/cells[(team, zone)]["n"]*100, 3) for zone in zones] + [round(raw_rates[team]*100, 3), round(estimates[team]["rate"]*100, 3)]} for team in TEAMS]},
        "findings": [f"{team}：近似95%区间{estimates[team]['low']:.2%}至{estimates[team]['high']:.2%}，权重有效样本量{estimates[team]['effective_n']:.1f}。" for team in TEAMS] + ["只使用同日同区域配齐的观察窗；每个区域的A/B两队使用同一组日期。", "合计先累加合格数与观察数再求比；不平均每日比率。", "目标权重在两队间保持一致；样本构成不同不能直接当成队伍绩效差异。"],
        "method": metadata()["method"], "warnings": warnings,
        "pairing": {"paired_windows": len(report["paired"]), "excluded_windows": len(report["excluded"]), "days": day_count,
                    "coverage": coverage, "excluded": report["excluded"], "paired": report["paired"]},
    }
