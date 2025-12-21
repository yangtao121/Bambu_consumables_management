# 耗材消耗重复录入问题诊断指南

## 概述

本指南说明如何使用添加的日志来诊断和解决耗材消耗重复录入的问题。

## 日志关键点

### 1. 事件处理日志

在 `event_processor.py` 中添加了以下关键日志点：

- **事件处理开始**：记录每个事件的基本信息
  ```
  开始处理事件: printer_id=xxx, job_key=xxx, event_type=PrintEnded, occurred_at=xxx
  ```

- **打印任务状态变更**：记录任务状态的每一次变化
  ```
  打印任务状态变更: job_id=xxx, event_type=PrintEnded, gcode_state=FINISH, old_status=running, new_status=ended
  ```

- **打印任务开始/结束/失败**：记录任务生命周期事件
  ```
  打印任务结束: job_id=xxx, old_status=running, new_status=ended, event_type=PrintEnded
  ```

- **结算触发**：记录何时触发耗材结算
  ```
  准备结算耗材消耗: job_id=xxx, status=ended, ended_at=xxx
  使用AMS校准结算模式: job_id=xxx
  ```

### 2. 库存变更日志

在 `stock_service.py` 中添加了详细的库存变更日志：

- **库存变更开始**：记录每次库存变更的详细信息
  ```
  库存变更开始: stock_id=xxx, material=PLA, color=白色, before=1000g, delta=-50g, effective_delta=-50g, after=950g, kind=consumption, reason=xxx, job_id=xxx
  ```

- **库存变更完成**：记录变更后的状态
  ```
  库存变更完成: stock_id=xxx, ledger_id=xxx, new_remaining=950g
  ```

### 3. 消耗记录创建日志

在 `event_processor.py` 中添加了消耗记录创建的详细日志：

- **幂等性检查**：记录是否已存在相同的消耗记录
  ```
  消耗记录已存在，跳过创建: job_id=xxx, tray_id=1, segment_idx=0
  ```

- **消耗记录创建**：记录每个新创建的消耗记录
  ```
  创建消耗记录(AMS校准-剩余量差值): id=xxx, job_id=xxx, stock_id=xxx, tray_id=1, grams=50, source=ams_remain_start_end_grams, confidence=medium
  ```

### 4. 结算流程日志

添加了两种结算模式的详细日志：

- **预扣结算模式**：记录预扣结算的各个阶段
  ```
  开始预扣结算流程: job_id=xxx, status=ended
  预扣结算参数: job_id=xxx, is_cancelled=false, progress_pct=100.0, progress_frac=1.0
  预扣结算完成: job_id=xxx, settled_at=xxx
  ```

- **AMS校准结算模式**：记录AMS校准结算的各个阶段
  ```
  AMS校准结算开始: job_id=xxx, trays_seen=[1,2], start_remain_by_tray={1: 50.0, 2: 75.0}
  AMS托盘剩余量: job_id=xxx, start_remain_by_tray={1: 50.0}, end_remain_by_tray={1: 40.0}
  AMS校准结算完成: job_id=xxx, settled_at=xxx
  ```

## 诊断步骤

### 1. 检查事件重复

检查日志中是否有重复的 `PrintEnded` 或 `PrintFailed` 事件：

```bash
grep "PrintEnded\|PrintFailed" /tmp/consumption_test.log
```

### 2. 检查结算重复触发

检查是否有多次结算触发：

```bash
grep "准备结算耗材消耗" /tmp/consumption_test.log
```

### 3. 检查库存变更重复

检查是否有重复的库存变更：

```bash
grep "库存变更开始" /tmp/consumption_test.log | grep "job_id=特定任务ID"
```

### 4. 检查消耗记录创建

检查是否有重复的消耗记录创建：

```bash
grep "创建消耗记录" /tmp/consumption_test.log | grep "job_id=特定任务ID"
```

### 5. 检查幂等性检查

检查幂等性检查是否正常工作：

```bash
grep "消耗记录已存在" /tmp/consumption_test.log
```

## 常见问题及解决方案

### 1. 事件重复

如果发现同一打印任务有多个结束事件，可能是打印机固件或网络问题。解决方案：
- 在事件处理器中添加去重逻辑，基于任务ID和事件类型
- 增加事件处理的时间窗口检查

### 2. 结算重复触发

如果发现结算被多次触发，可能是状态变更导致多次满足结算条件。解决方案：
- 添加结算状态检查，确保每个任务只结算一次
- 在结算开始时设置临时锁，防止并发结算

### 3. 幂等性检查失效

如果幂等性检查未能阻止重复记录，可能是索引或查询问题。解决方案：
- 检查数据库索引是否正确创建
- 验证幂等性检查的查询条件是否准确

## 测试

使用提供的测试脚本验证日志输出：

```bash
cd backend
python test_logging.py
```

查看日志文件：

```bash
tail -f /tmp/consumption_test.log
```

## 注意事项

1. 日志可能会产生大量输出，特别是在繁忙的打印环境中
2. 考虑在生产环境中调整日志级别，仅记录关键信息
3. 定期清理日志文件，避免占用过多磁盘空间
