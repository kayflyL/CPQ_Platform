"""
默认规格书模板配置

简化后的结构：
- branding: 品牌信息（用户可自定义）
- display_options: 显示控制开关（用户可调整）
"""

def get_default_template_config() -> dict:
    """返回默认模板的完整配置"""
    return {
        # 品牌配置（用户可自定义）
        "branding": {
            "logo_url": "",
            "company_name": "",
            "tagline": "",
            "doc_title": "配置规格书 / Server Build Specification",
            "contact_phone": "",
            "contact_email": "",
            "address": "",
            "footer_note": "",
            # 报价条款（公司标准口径；留空则该条不显示）
            "commercial_terms": {
                "currency": "报价单位：人民币含税",
                "validity": "因 KP 波动，报价有效期 2 天",
                "delivery": "交付周期为签订合同收到预付款后 2-4 周内，合同签订后预付 50% 预付款",
                "shipping": "寄送至中国大陆境内",
            },
        },

        # 显示控制（默认全部显示）
        "display_options": {
            "show_price_column": True,
            "show_chassis_total": True,
            "show_kp_subtotal": True,
            "show_grand_total": True,
            "show_footer_check": True,
            "show_commercial_terms": True,
        }
    }
