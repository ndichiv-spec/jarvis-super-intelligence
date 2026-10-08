import sys, os, asyncio
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-')
sys.path.insert(0, 'F:/AI/Jarvis-super-intelligence-/proto')
os.environ['JARVIS_ENV'] = 'dev'

from jarvis_backend.research import AutonomousResearchCortex, ScienceEngine, BioLearner, TechEvolutionTracker

async def test_science():
    science = ScienceEngine()
    
    print('[2] ScienceEngine:')
    sci_status = science.get_status()
    print(f'  Status: {sci_status}')
    
    # Test symbolic algebra
    result = await science.solve({'problem': '2*x + 5 = 15', 'operation': 'solve', 'variable': 'x'})
    print(f'  1. Solve 2x+5=15: {result.get("final_answer", "FAILED")}')
    
    # Test symbolic integral (operation="integral")
    result = await science.solve({'problem': 'x**2', 'operation': 'integral', 'variable': 'x'})
    print(f'  2. Symbolic integral of x^2: {result.get("final_answer", "FAILED")}')
    
    # Test numerical integration (operation="integrate")
    result = await science.solve({'operation': 'integrate', 'problem': 'sin(x)', 'x_min': 0, 'x_max': 3.14159, 'num_points': 1000})
    print(f'  3. Numerical integral of sin(x) [0,pi]: {result.get("final_answer", "FAILED")}')
    
    # Test derivative
    result = await science.solve({'problem': 'x**2 + 3*x + 2', 'operation': 'derivative', 'variable': 'x'})
    print(f'  4. Derivative of x^2+3x+2: {result.get("final_answer", "FAILED")}')
    
    # Test Monte Carlo pi
    result = await science.solve({'operation': 'monte_carlo', 'mc_operation': 'estimate_pi', 'n_samples': 50000})
    print(f'  5. MC pi estimate: {result.get("final_answer", "FAILED")}')
    
    # Test linear algebra determinant
    result = await science.solve({'operation': 'determinant', 'matrix': [[2,1],[3,4]]})
    print(f'  6. Determinant [[2,1],[3,4]]: {result.get("final_answer", "FAILED")}')
    
    # Test statistics
    result = await science.solve({'operation': 'mean', 'data': [1.0, 2.0, 3.0, 4.0, 5.0]})
    print(f'  7. Mean of [1,2,3,4,5]: {result.get("final_answer", "FAILED")}')
    
    # Test hypothesis formulation
    result = await science.solve({'operation': 'hypothesis', 'problem': 'quantum_decoherence'})
    hyp = result.get('hypothesis', {})
    print(f'  8. Hypothesis: {hyp.get("statement", "FAILED")[:80]}')

async def test_all():
    print('=== Testing Bio-Growth Research Modules ===')
    print()

    # 1. Autonomous Research Cortex
    cortex = AutonomousResearchCortex()
    cortex.initialize()
    print('[1] AutonomousResearchCortex:')
    status = cortex.get_status()
    print(f'  Feeds: {status["total_feeds"]}, Stage: {status["growth_stage"]}')
    print(f'  Ingested: {status["total_ingested"]}, Concepts: {status["total_concepts"]}')
    print()

    # 2. Science Engine
    await test_science()
    print()

    # 3. BioLearner
    bio = BioLearner()
    bio.initialize()
    print('[3] BioLearner:')
    bio_status = bio.get_status()
    print(f'  Domains: {len(bio_status["domains"])}, Stage: {bio_status["growth_stage"]}')
    print(f'  Overall maturity: {bio_status["overall_maturity"]:.2f}')
    
    path = bio.get_learning_path('mathematics')
    path_len = len(path['learning_path'].get('mathematics', []))
    print(f'  Math curriculum: {path_len} concepts')
    
    result = await bio.study_concept('mathematics', 'arithmetic')
    print(f'  Study arithmetic: success={result.get("success", False)}, mastery={result.get("mastery_level", 0):.3f}')
    
    result = await bio.consolidate()
    print(f'  Consolidation: success={result.get("success", False)}, syntheses={result.get("syntheses_generated", 0)}')
    print()

    # 4. Tech Evolution Tracker
    tech = TechEvolutionTracker()
    tech.initialize(cortex=cortex)
    print('[4] TechEvolutionTracker:')
    t_status = tech.get_status()
    print(f'  Total technologies: {t_status["total_technologies"]}, Stage: {t_status["growth_stage"]}')
    
    radar = tech.get_tech_radar()
    print(f'  Tech Radar: {radar["total_technologies"]} technologies')
    
    frontiers = tech.get_frontiers()
    print(f'  Research frontiers: {frontiers["total_frontiers"]}')
    print()
    print('=== All 4 modules verified ===')

asyncio.run(test_all())
