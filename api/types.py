from typing import Optional, Union, Literal

from pydantic import BaseModel, Field, ConfigDict


class TaskDispatch(BaseModel):
    mirror: Union[str, dict]
    uuid: str = ''
    SCULPTOR_MODEL: str = ''
    SCULPTOR_VL_MODEL: str = ''


class Difference(BaseModel):
    name: str
    path: str
    comment: str
    improve: str


class InteractionTest(BaseModel):
    测试点编号: int
    测试点名称: str
    操作步骤: list[str]
    预期结果: str


class Box(BaseModel):
    x: float
    y: float
    w: float
    h: float


class TreeNode(BaseModel):
    type: str = "Unrecognized Node Type"
    name: str = 'Unrecognized Element'
    path: str = ''
    children: 'Optional[list[TreeNode]]' = None


class Code(BaseModel):
    path: str
    content: str

    def __init__(self, path: str, content: str, **data) -> None:
        super().__init__(path=path, content=content, **data)
        self.path = path
        self.content = content.replace('\r\n', '\n')


class BaseRequest(BaseModel):
    response_style: Literal['sculptor', 'mirror'] = 'sculptor'
    lang: str = 'zh-hans'
    code_id: str
    mock: bool = False
    model: Optional[str] = None
    vl_model: Optional[str] = None


class InterImproveRequestStep(BaseModel):
    target: str
    practice: str


class InterImproveRequestImprovement(BaseModel):
    task: str
    expectation: str
    steps: list[InterImproveRequestStep]


class InterImproveRequest(BaseRequest):
    code: list[Code]
    improvements: list[InterImproveRequestImprovement]


class GenUIStructureRequest(BaseRequest):
    type: str = 'gen_ui_structure'
    design: str
    code: list[Code]


class CompareRequest(BaseRequest):
    type: str = 'compare'
    node: TreeNode
    design: str
    render: str
    strict: bool = True


class CodeImproveRequest(BaseRequest):
    type: str = 'code_improve'
    code: list[Code]
    diff: list[Difference]


class ChatImproveRequest(BaseRequest):
    type: str = 'chat_improve'
    query: str
    code: list[Code]
    code_file: str = ''
    code_line: int = -1
    breakpoint: int = 0
    node: Optional[TreeNode] = None


class VisualCodeImproveRequest(ChatImproveRequest):
    type: str = 'visual_code_improve'
    screenshot: str


class LocateCodeRequest(BaseRequest):
    code: list[Code]
    screenshot: str


class ReplaceComponentRequest(BaseRequest):
    original_code: list[Code]
    new_component: list[Code]
    code_file: str
    code_line: int


class FixStyleRequest(BaseRequest):
    type: str = 'fix_style'
    
    html: str
    
    code: list[Code] = []
    
    file: str = ''
    
    line: int = 0
    
    related_files: list[str] = []
    
    design: str = ''
    
    node: dict = {}

    render: str = ''
    
    layout_size: Union[Literal['sm', 'md', 'lg', 'xl', '2xl', 'default'], int, tuple[int, int]] = 'default'


class HTMLNodeAttributes(BaseModel):
    id: Optional[str] = None
    class_: str = Field(default='', alias='class')


class HTMLNodeBoundingRect(BaseModel):
    top: float
    left: float
    width: float
    height: float


class HTMLNodeData(BaseModel):
    tagName: str
    textContent: str
    filePath: str
    lineStart: int
    lineEnd: Optional[int] = None
    attributes: HTMLNodeAttributes
    boundingRect: HTMLNodeBoundingRect
    screenshot: str = ''  # 只有根节点有用
    children: list['HTMLNodeData']


class FigmaToTailwindRequest(BaseModel):
    type: str = 'figma_to_tailwind'
    file_key: str
    node_id: str
    token: str
    
    use_cache: bool = True
    
    root_node_id: str = ''


class FigmaToTailwindResponse(BaseModel):
   
    html: str
    
    warnings: list[tuple[str, str]]


class DesignFixRequest(BaseRequest):
    temp_message_id: str


class DesignFixSelectRequest(DesignFixRequest):
    type: Literal['design_fix/select']
    html_data: HTMLNodeData


class DesignFixSearchRequest(DesignFixRequest):
    type: Literal['design_fix/search']


class DesignFixSearchResponse(BaseModel):
    class SimilarNode(BaseModel):
        name: str = ''
        nodeIds: list[str] = []
        similarity: float

    class HuntResult(BaseModel):
        groupName: str
        similarNodes: list['DesignFixSearchResponse.SimilarNode']


class DesignFixPlanRequest(DesignFixRequest):
    class SimilarNode(BaseModel):
        name: str = ''
        node_ids: list[str]
        annotations: list = []

    type: Literal['design_fix/plan']
    design_nodes: list[SimilarNode]
    mock_single_file: bool = False


class DesignFixPlanResponse(BaseModel):
    class SimilarNode(BaseModel):
        name: str = ''
        nodeIds: list[str] = []

    class FixPlan(BaseModel):
        type: Literal['MODIFY', 'NEW']
        file: str
        line: int
        designNodes: list['DesignFixPlanResponse.SimilarNode']
        needConfirm: bool


class DesignFixFixRequest(DesignFixRequest):
    class SimilarNode(BaseModel):
        name: str = ''
        node_ids: list[str] = Field(alias='nodeIds')
        annotations: list = []

        model_config = ConfigDict(populate_by_name=True)

    class FixPlan(BaseModel):
        type: Literal['MODIFY', 'NEW']
        file: str
        line: int
        design_nodes: list['DesignFixFixRequest.SimilarNode'] = Field(alias='designNodes')

        model_config = ConfigDict(populate_by_name=True)

    type: Literal['design_fix/fix']
    fix_plan: list[FixPlan]


class DesignFixBacktestRequest(DesignFixRequest):
    type: Literal['design_fix/backtest']
    html_data: HTMLNodeData
    user_prompt: str


class Figma2HTMLRequest(BaseModel):
    class DataModel(BaseModel):
        rest_api_file: dict
        tokens: dict[str, str]

    figma_html: 'Figma2HTMLRequest.DataModel'


class Figma2HTMLResponse(BaseModel):
    class Warning(BaseModel):
        nodeId: str
        warning: str

    html: str
    warnings: list['Figma2HTMLResponse.Warning']
