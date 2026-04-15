# Agentic RAG 解析补充样例文件包

本文件包用于补充第一阶段以 Markdown 为主的知识库测试集，重点验证：

- PDF / DOCX / PPTX 解析质量
- 标题层级提取
- 表格与列表提取
- 页码 / 幻灯片页号定位
- 图片、模板页、占位符与正文的区分
- OCR/扫描件降级策略

## 文件清单

### PDF
1. `pdf/lightrag_2410.05779.pdf`
   - 类型：学术论文 PDF
   - 特点：章节层级清晰、双栏/学术排版、公式/图表/参考文献
   - 适合测试：基础 PDF 文本提取、章节切分、引用定位

2. `pdf/close_brothers_annual_report_2024.pdf`
   - 类型：年报 PDF
   - 特点：页数多、目录复杂、表格密集、财务数据丰富
   - 适合测试：长文档解析、表格区域处理、页码与标题导航

3. `pdf/epa_sample_letter_scanned.pdf`
   - 类型：扫描件 PDF
   - 特点：图像型页面、文本层较弱/需 OCR 兜底
   - 适合测试：扫描件识别、OCR 回退、低质量 PDF 降级策略

### DOCX
4. `docx/optional_syllabus_template_sample.docx`
   - 类型：课程大纲模板
   - 特点：标题、列表、表格、规范化段落较多
   - 适合测试：DOCX 段落样式、标题层级、列表提取

5. `docx/epa_templates.docx`
   - 类型：官方模板文档
   - 特点：模板字段、说明文本、表单式结构
   - 适合测试：模板占位符识别、结构化段落提取

6. `docx/nih_protocol_template.docx`
   - 类型：临床试验方案模板
   - 特点：长文档、规范章节、复杂说明文字
   - 适合测试：长 DOCX 解析、标题树、跨节切分

### PPTX
7. `pptx/utah_defense_presentation_template.pptx`
   - 类型：答辩模板
   - 特点：模板页、占位符、图片位、少量正文
   - 适合测试：模板页识别、幻灯片标题提取

8. `pptx/uw_simple_powerpoint_template.pptx`
   - 类型：品牌模板
   - 特点：多母版、多版式、主题样式明显
   - 适合测试：母版与正文区分、空白模板页过滤

9. `pptx/hinton_nn_lecture12.pptx`
   - 类型：教学课件
   - 特点：内容丰富、公式、图片、分点文本较多
   - 适合测试：PPTX 正文提取、页级切分、图文混排解析

## 推荐使用顺序

### 第一轮：最小可用解析验证
- `lightrag_2410.05779.pdf`
- `optional_syllabus_template_sample.docx`
- `hinton_nn_lecture12.pptx`

目标：先跑通 PDF / DOCX / PPTX 三类文件的基本解析、入库、切分、检索。

### 第二轮：复杂结构验证
- `close_brothers_annual_report_2024.pdf`
- `epa_templates.docx`
- `uw_simple_powerpoint_template.pptx`

目标：验证长文档、模板页、表格密集内容的处理质量。

### 第三轮：边界与降级验证
- `epa_sample_letter_scanned.pdf`
- `nih_protocol_template.docx`
- `utah_defense_presentation_template.pptx`

目标：验证扫描件 OCR、超长 DOCX、模板型 PPTX 的降级策略与异常处理。

## 建议额外记录的评测字段

对每个文件，建议在解析日志里记录：

- `parse_success`
- `page_or_slide_count`
- `heading_count`
- `table_count`
- `image_count`
- `empty_page_count`
- `ocr_used`
- `chunk_count`
- `avg_chunk_length`
- `citation_page_available`
- `notes`

## 建议的验收标准

- PDF / DOCX / PPTX 三类文件均可成功入库
- 标题层级基本正确
- 表格与列表不大面积丢失
- 扫描件可触发 OCR 或明确降级提示
- PPTX 模板页不会大量污染正文检索
- 回答引用能定位到页码或幻灯片页号
