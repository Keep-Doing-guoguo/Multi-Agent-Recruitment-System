import unittest

from recruitment_system.tools.document_extraction import DocumentExtractionTool


class DocumentExtractionToolTest(unittest.TestCase):
    def test_long_crlf_jd_text_is_treated_as_inline_text(self) -> None:
        jd_text = (
            "职位: 算法工程师\r\n\r\n"
            "岗位职责:\r\n"
            "- 负责机器学习、深度学习或大模型相关算法的设计、训练、评估和上线\r\n"
            "- 结合业务场景完成特征工程、模型优化、效果分析和实验迭代\r\n\r\n"
            "岗位要求:\r\n"
            "- 本科及以上学历，计算机、人工智能、数学、统计学或相关专业\r\n"
            "- 3 年以上算法工程或机器学习项目经验\r\n"
            "- 熟悉 Python、PyTorch 或 TensorFlow，具备扎实的数据结构和算法基础"
        )

        tool = DocumentExtractionTool()
        result = tool.run(jd_text, "jd")

        self.assertFalse(result.errors)
        self.assertEqual(result.source, "inline_text")
        self.assertEqual(result.file_type, "text")
        self.assertEqual(result.extracted_text, jd_text)


if __name__ == "__main__":
    unittest.main()
