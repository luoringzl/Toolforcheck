# 离线人事材料批量核验工具（MVP）

完全离线运行，用于按人员批量读取 DOCX、PDF、JPG、JPEG、PNG，提取身份、学历、工作经历字段并生成 Excel 核验报告。

## 已实现

- 直接读取用户已经建立好的人员姓名一级子文件夹；不创建档案、不分组、不移动或重命名文件
- DOCX 正文/表格、电子 PDF 文本直接提取
- 扫描 PDF 和图片使用本机 Tesseract OCR（不调用网络）
- 身份证图像质量门禁：模糊、强反光、严重旋转、尺寸不足时退回
- 身份证号码格式、出生日期、性别顺序码校验
- 姓名、出生日期、毕业院校、毕业时间、证书编号提取
- 企业名称、工作起止时间和工作年限提取
- 企业简称硬性退回；可导入本地工商企业全称名录进行严格匹配
- 输出人员总表、字段差异、工作经历、材料清单、退回清单、运行日志
- 所有处理均在本机完成

## Windows源码运行

1. 安装 Python 3.11 或 3.12（安装时勾选 Add Python to PATH）。
2. 安装 Tesseract OCR，并安装 `chi_sim` 简体中文语言包。
3. 在本目录执行：

```powershell
py -m pip install -r requirements.txt
py app.py
```

如 Tesseract 不在 PATH，可设置环境变量：

```powershell
$env:TESSERACT_CMD="C:\Program Files\Tesseract-OCR\tesseract.exe"
py app.py
```

## 文件组织

```text
待审核人员/
├─ 张三_1234/
│  ├─ 身份证正面.jpg
│  ├─ 身份证反面.jpg
│  ├─ 简历.docx
│  ├─ 毕业证.png
│  ├─ 劳动合同.pdf
│  └─ 离职证明.pdf
└─ 李四_5678/
   └─ ...
```

## 企业全称名录

可选 CSV 或 XLSX，第一列标题建议为 `企业全称`，每行一个工商登记全称。启用名录后：

- 完全一致：通过企业名称校验
- 明显简称：`该企业信息为简称，请补充与工商信息一致的全称`
- 形式完整但未收录：`无法确认是否为工商登记全称，请补充证明或更新企业名录`
- 相近但不一致：不自动通过

## 命令行

```powershell
py -m verifier.cli "D:\待审核人员" --output "D:\核验报告.xlsx" --company-registry "D:\企业全称.xlsx"
```

## 重要说明

这是规则完整、可运行的 MVP，并非联网背调或证件真伪鉴定工具。图片质量阈值和各类材料字段模板需要用脱敏的真实样本校准。软件不会对模糊身份证字符进行猜测或用其他材料自动补全。

## Windows安装包构建

正式安装包将Python运行环境、Tesseract OCR、简体中文和方向检测模型全部打包，不要求使用者另装Python或OCR。Windows构建机执行：

```powershell
.\build\windows\build.ps1
```

输出位于 `dist-installer`。仓库也包含可手动触发的Windows自动构建流程。
