"""
数据底座 — 本体对象定义
基于恩同真实数据模型：配件/品牌子渠道/供应商/客户/报价单
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class PricingMode(Enum):
    """四种定价模式（基于真实Excel分析）"""
    STANDARD = "standard"        # 牌价 × 折扣矩阵
    FIXED_STOCK = "fixed_stock"  # 库存一口价，覆盖所有规则
    COST_BASED = "cost_based"    # 含税进价，零利润
    NEGOTIATED = "negotiated"    # 一单一议，人工定价


class QualityGrade(Enum):
    """质量档位"""
    A_PLUS = "A+"      # 原厂/OEM
    B_PLUS = "B+"      # 原厂配套/售后
    C_PLUS = "C+"      # 好质量售后
    D = "D"            # 便宜/副厂


class TradeTerm(Enum):
    """贸易术语"""
    FOB = "FOB"
    CNF = "CNF"
    CIF = "CIF"


class PaymentTerm(Enum):
    """付款条件，按风险从低到高"""
    PREPAID = "prepaid"           # 发货前付清全款
    AGAINST_BL = "against_bl"     # 见提单付尾款
    NET_15 = "net_15"             # 收货后15天
    NET_30 = "net_30"             # 收货后30天
    NET_60 = "net_60"             # 收货后60天
    NET_90 = "net_90"             # 收货后90天


class WarrantyLevel(Enum):
    """质保档位"""
    NONE = "none"        # 不要质保
    STANDARD = "std"     # 正常质保
    EXTENDED = "ext"     # 超长质保


class Application(Enum):
    """应用场景"""
    TRUCK = "卡车"
    MINING_TRUCK = "矿卡"
    EXCAVATOR = "挖机"
    CONSTRUCTION = "工程机"
    GENERATOR = "发电机组"
    BUS = "大巴车"
    SPECIAL = "特种车"
    SHIP = "船舶"
    POWER_PACK = "动力包"


class ProductLine(Enum):
    """五条产品线"""
    FOTON_FUKANG = "福田福康"
    DONGFENG_CUMMINS = "东风康明斯"
    CUMMINS_CHINA = "康明斯中国"
    DONGFENG_TRUCK = "东风商用车"
    SCHAEFFLER = "德国舍弗勒"


class Region(Enum):
    """六大地区"""
    EAST_ASIA = "东亚"
    SE_ASIA = "东南亚"
    SOUTH_ASIA = "南亚"
    MIDDLE_EAST = "中东"
    AFRICA = "非洲"
    CIS = "独联体(俄罗斯等)"
    EAST_EUROPE = "东欧"
    LATIN_AMERICA = "拉美"


@dataclass
class BrandChannel:
    """品牌子渠道（福田下面有10+个）"""
    name: str                    # A2080, 卡友配, E9300, 东亚, BOSCH...
    product_line: ProductLine
    discount_matrix: dict = field(default_factory=dict)  # 二维折扣矩阵
    # discount_matrix = {
    #     (0, 5): {"lt": None, "gte": None},           # <=5元 无折扣
    #     (5, 50): {"lt": 17, "gte": 15},              # 5-50元 15-17%
    #     (50, 1000): {"lt": 23, "gte": 24, "threshold": 30},  # <30件23%, >=30件24%
    #     (1000, 10000): {"lt": 24, "gte": 25.5, "threshold": 10},
    # }
    cap_discount: float = 25.5           # 顶格上限
    min_order_amount: float = 0.0        # 品牌最低起订金额 (如卡友配满3万)
    supplier_contact: str = ""           # 供应商联系人
    notes: str = ""


@dataclass
class Part:
    """配件"""
    oe_number: str                       # OE号 (如 5264231)
    alt_oe_numbers: list = field(default_factory=list)  # 替代OE号
    name_cn: str = ""                    # 中文品名
    name_ru: str = ""                    # 俄文品名
    name_en: str = ""                    # 英文品名
    brand_channel: str = ""              # 品牌子渠道名
    supply_number: str = ""              # 供货号
    list_price: float = 0.0              # 牌价
    engine_model: str = ""               # 适配发动机 (如 ISF2.8)
    vehicle_model: str = ""              # 适配车型 (如 福田欧曼)
    emission_std: str = ""               # 排放标准 (欧3/4/5)
    unit: str = "PC"                     # 单位
    pricing_mode: PricingMode = PricingMode.STANDARD
    fixed_stock_price: float = 0.0       # 库存一口价
    cost_with_tax: float = 0.0           # 含税进价
    cost_without_tax: float = 0.0        # 不含税进价
    min_order_qty: float = 0.0           # 最小起订量
    supplier_name: str = ""              # 供应商名
    lead_time_days: int = 0              # 交期(天)
    product_line: ProductLine = ProductLine.FOTON_FUKANG
    application: list = field(default_factory=list)  # 适用场景
    is_active: bool = True               # 是否在售 (原厂停产=false)
    replacement_part: str = ""           # 替代配件OE号
    competitor_price: float = 0.0        # 竞品参考价
    notes: str = ""


@dataclass
class Supplier:
    """供应商"""
    name: str
    brands: list = field(default_factory=list)   # 供应的品牌
    contact: str = ""
    payment_terms: str = ""
    reliability: str = ""                        # 可靠性评价


@dataclass
class Customer:
    """客户"""
    name_cn: str = ""
    name_en: str = ""
    country: str = ""
    region: Region = Region.CIS
    star_level: int = 1                 # 一星~七星
    annual_purchase: float = 0.0        # 年采购额(元)
    preferred_trade: TradeTerm = TradeTerm.FOB
    preferred_payment: PaymentTerm = PaymentTerm.PREPAID
    payment_punctuality: str = ""       # 付款准时度
    is_blacklisted: bool = False
    tags: list = field(default_factory=list)  # 老客户/新客户/展会/平台...
    notes: str = ""


@dataclass
class QuotationLine:
    """报价单行"""
    oe_number: str
    part_name_ru: str = ""
    quality_grade: QualityGrade = QualityGrade.A_PLUS
    quantity: int = 1
    unit: str = "PC"
    unit_price: float = 0.0
    total_amount: float = 0.0
    pricing_mode: PricingMode = PricingMode.STANDARD
    list_price: float = 0.0             # 原始牌价
    discount_pct: float = 0.0           # 实际折扣%
    discount_coeff: float = 1.0         # 折扣系数
    remark: str = ""


@dataclass
class Quotation:
    """报价单"""
    id: str = ""
    customer_name: str = ""
    customer_contact: str = ""
    date: str = ""                      # ISO date
    lines: list = field(default_factory=list)  # QuotationLine[]
    trade_term: TradeTerm = TradeTerm.FOB
    payment_term: PaymentTerm = PaymentTerm.PREPAID
    total_amount: float = 0.0
    status: str = "draft"               # draft/pending_review/approved/sent
    created_by: str = ""
    reviewed_by: str = ""
    approved_by: str = ""
    trace_log: list = field(default_factory=list)  # 审计日志
