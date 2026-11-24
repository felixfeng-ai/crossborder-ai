"""LangGraph Agent 工作流：模型、工具和业务上下文编排。

VeyaShip - LangGraph Agent Workflows.

Multi-step AI agents for complex tasks like:
- Product research and listing optimization
- Cross-platform listing adaptation
- Competitive analysis
- Bulk content generation with review"""

from typing import Any, Dict, List, Optional, TypedDict, Annotated, Literal

from langgraph.graph import StateGraph, END

from app.services.ai.deepseek import DeepSeekService
from app.services.ai.replicate import ReplicateService
from app.services.ai.rag import RAGService


# --- State Definition ---
class AgentState(TypedDict):
    """State passed through the LangGraph workflow."""
    product_title: str
    product_description: str
    features: str
    platform: str
    target_language: Optional[str]
    tone: str
    persona_block: Optional[str]
    source_content: Optional[str]
    generated_title: Optional[str]
    generated_description: Optional[str]
    generated_bullet_points: Optional[List[str]]
    seo_title: Optional[str]
    seo_description: Optional[str]
    image_urls: Optional[List[str]]
    review_feedback: Optional[str]
    iteration_count: int
    max_iterations: int
    final_output: Optional[Dict[str, Any]]


class ListingAgent:
    """LangGraph-powered agent for automated listing generation."""

    def __init__(self):
        self.llm = DeepSeekService()
        self.image_gen = ReplicateService()
        self.rag = RAGService()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Construct the agent workflow graph."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("analyze_product", self._analyze_product)
        workflow.add_node("generate_title", self._generate_title)
        workflow.add_node("generate_description", self._generate_description)
        workflow.add_node("generate_bullets", self._generate_bullets)
        workflow.add_node("optimize_seo", self._optimize_seo)
        workflow.add_node("generate_image", self._generate_image)
        workflow.add_node("review_output", self._review_output)
        workflow.add_node("finalize", self._finalize)

        # Set entry point
        workflow.set_entry_point("analyze_product")

        # Add edges
        workflow.add_edge("analyze_product", "generate_title")
        workflow.add_edge("generate_title", "generate_description")
        workflow.add_edge("generate_description", "generate_bullets")
        workflow.add_edge("generate_bullets", "optimize_seo")
        workflow.add_edge("optimize_seo", "generate_image")
        workflow.add_edge("generate_image", "review_output")

        # Conditional edge: review -> finalize or regenerate
        workflow.add_conditional_edges(
            "review_output",
            self._should_continue,
            {
                "finalize": "finalize",
                "regenerate": "generate_title",  # Loop back
                "end": END,
            },
        )

        workflow.add_edge("finalize", END)

        return workflow.compile()

    async def _analyze_product(self, state: AgentState) -> Dict:
        """Analyze product info and extract key selling points."""
        prompt = (
            f"Analyze this product for {state['platform']} listing optimization:\n"
            f"Title: {state['product_title']}\n"
            f"Description: {state['product_description'][:500]}\n"
            f"Features: {state['features']}\n\n"
            f"Identify: 1) Key selling points 2) Target audience 3) Competitive angle"
        )

        analysis = await self.llm.generate(
            "You are a product analyst for cross-border e-commerce.",
            prompt,
            max_tokens=800,
        )

        return {"source_content": analysis}

    async def _generate_title(self, state: AgentState) -> Dict:
        """Generate an optimized product title."""
        title = await self.llm.generate(
            f"You are an expert {state['platform']} listing copywriter.",
            (
                f"Generate a compelling, SEO-optimized product title (max 200 chars) "
                f"for {state['platform']} in a {state['tone']} tone.\n\n"
                f"Product: {state['product_title']}\n"
                f"Key Info: {state['source_content'][:300]}\n"
                f"Target Language: {state.get('target_language', 'en')}"
            ),
            max_tokens=300,
            persona_block=state.get("persona_block"),
        )

        return {"generated_title": title.strip(), "iteration_count": state["iteration_count"] + 1}

    async def _generate_description(self, state: AgentState) -> Dict:
        """Generate a full product description."""
        description = await self.llm.generate_product_description(
            product_title=state.get("generated_title") or state["product_title"],
            product_features=state["features"],
            tone=state["tone"],
            platform=state["platform"],
            target_language=state.get("target_language"),
            persona_block=state.get("persona_block"),
        )

        return {"generated_description": description}

    async def _generate_bullets(self, state: AgentState) -> Dict:
        """Generate bullet points."""
        bullets = await self.llm.generate_bullet_points(
            product_title=state.get("generated_title") or state["product_title"],
            features=state["features"],
            platform=state["platform"],
            persona_block=state.get("persona_block"),
        )

        return {"generated_bullet_points": bullets}

    async def _optimize_seo(self, state: AgentState) -> Dict:
        """Optimize content for search engines."""
        seo = await self.llm.optimize_seo(
            title=state.get("generated_title") or state["product_title"],
            description=state.get("generated_description") or state["product_description"],
            platform=state["platform"],
            persona_block=state.get("persona_block"),
        )

        return seo

    async def _generate_image(self, state: AgentState) -> Dict:
        """Generate product image via FLUX."""
        try:
            images = await self.image_gen.generate_product_image(
                product_title=state.get("generated_title") or state["product_title"],
                product_description=state.get("generated_description"),
            )
            return {"image_urls": images}
        except Exception:
            return {"image_urls": []}

    async def _review_output(self, state: AgentState) -> Dict:
        """Self-review the generated content for quality."""
        if state.get("iteration_count", 0) >= state.get("max_iterations", 2):
            return {"review_feedback": "Max iterations reached"}

        review_prompt = (
            f"Review this {state['platform']} listing for quality and completeness:\n"
            f"Title: {state.get('generated_title')}\n"
            f"Description: {state.get('generated_description', '')[:300]}\n"
            f"Bullets: {state.get('generated_bullet_points', [])}\n\n"
            f"Rate 1-10 and suggest improvements. Be critical."
        )

        review = await self.llm.generate(
            "You are a quality assurance reviewer for e-commerce listings.",
            review_prompt,
            max_tokens=500,
        )

        return {"review_feedback": review}

    def _should_continue(
        self, state: AgentState
    ) -> Literal["finalize", "regenerate", "end"]:
        """Decide whether to finalize, regenerate, or end."""
        if state.get("iteration_count", 0) >= state.get("max_iterations", 2):
            return "finalize"
        if "improve" in (state.get("review_feedback") or "").lower():
            return "regenerate"
        return "finalize"

    async def _finalize(self, state: AgentState) -> Dict:
        """Compile final output."""
        return {
            "final_output": {
                "title": state.get("generated_title"),
                "description": state.get("generated_description"),
                "bullet_points": state.get("generated_bullet_points"),
                "seo_title": state.get("seo_title"),
                "seo_description": state.get("seo_description"),
                "image_urls": state.get("image_urls"),
                "iteration_count": state.get("iteration_count"),
            }
        }

    async def run(
        self,
        product_title: str,
        product_description: str = "",
        features: str = "",
        platform: str = "amazon",
        tone: str = "professional",
        target_language: Optional[str] = None,
        max_iterations: int = 2,
        persona_block: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the full listing generation agent workflow.

        Args:
            product_title: Product name.
            product_description: Product description text.
            features: Key features / specs.
            platform: Target e-commerce platform.
            tone: Writing tone.
            target_language: Target language for translation.
            max_iterations: Maximum regeneration cycles.
            persona_block: 统一品牌档案块（CAP-04），注入各生成步 system prompt 顶部。

        Returns:
            Final generated listing content.
        """
        initial_state: AgentState = {
            "product_title": product_title,
            "product_description": product_description,
            "features": features,
            "platform": platform,
            "target_language": target_language,
            "tone": tone,
            "persona_block": persona_block,
            "source_content": None,
            "generated_title": None,
            "generated_description": None,
            "generated_bullet_points": None,
            "seo_title": None,
            "seo_description": None,
            "image_urls": None,
            "review_feedback": None,
            "iteration_count": 0,
            "max_iterations": max_iterations,
            "final_output": None,
        }

        result = await self.graph.ainvoke(initial_state)
        return result.get("final_output", {})
