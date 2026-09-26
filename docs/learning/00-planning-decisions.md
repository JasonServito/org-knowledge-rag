# Learning note 00: Planning decisions (pre-code)

These decisions were made before any code existed. An interviewer will ask about them first, because they reveal judgment. **Answer each one in your own words.** Then paste your answers into chat and ask for them to be graded.

The source for each answer is in brackets.

1. **Why a real public corpus instead of a synthetic company dataset?** [Blueprint §5.1]
   **A:**
2. **Why Kubernetes over GitLab and GOV.UK? What did you give up?** [ADR-001, validation gate §1 and §3]
   **A:**
3. **What problem does "enterprise RAG" have that plain semantic search doesn't?** [Blueprint core thesis, §2]
   **A:**
4. **What counts as a "version" in your system, and why not every commit?** [ADR-002 D1–D2]
   **A:**
5. **Why do you store both a release window and a date window?** [ADR-002 D3]
   **A:**
6. **What's the difference between `claimed_status` and `observed_stage`, and why keep both?** [ADR-002 D5, ADR-003 D2, validation gate §3]
   **A:**
7. **Why is authority mode-dependent instead of one ranking?** [ADR-003 D4]
   **A:**
8. **Why PostgreSQL + pgvector instead of a dedicated vector database?** [Blueprint §9, §13, §28]
   **A:**
9. **Why build a deliberately simple dense baseline first?** [Blueprint §19.3, product spec AC7]
   **A:**
10. **Why must you, not the AI, write the golden-set labels?** [`docs/ai-workflow.md` §5]
    **A:**
11. **Why deterministic metadata headers on chunks instead of LLM-generated context?** [Blueprint §11]
    **A:**
12. **Why EC2 instead of ECS/Fargate or Lambda, and how do you stay under $50/month?** [Blueprint §23, §27]
    **A:**
13. **Why a bounded LangGraph loop instead of a multi-agent system?** [Blueprint §17, §28]
    **A:**
14. **How do you avoid the system inventing a rationale that isn't in the corpus?** [Blueprint §18, product spec AC3]
    **A:**
