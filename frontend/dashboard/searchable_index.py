"""
JARVIS Searchable Codebase Index
===============================
Advanced search and indexing system for JARVIS codebase with intelligent
search capabilities, semantic understanding, and real-time indexing.

Features:
- Full-text search across codebase
- Semantic search with AI understanding
- Code pattern matching
- Dependency-based search
- Real-time indexing updates
- Search result ranking
- Advanced filtering options
- Search analytics
- Auto-suggestions
- Search history
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import hashlib
from pathlib import Path
from collections import defaultdict, Counter
import math

logger = logging.getLogger(__name__)


class SearchType(Enum):
    """Search type enumeration"""
    FULL_TEXT = "full_text"
    SEMANTIC = "semantic"
    PATTERN = "pattern"
    DEPENDENCY = "dependency"
    STRUCTURAL = "structural"
    METADATA = "metadata"
    HYBRID = "hybrid"


class SearchScope(Enum):
    """Search scope enumeration"""
    ENTIRE_CODEBASE = "entire_codebase"
    COMPONENTS_ONLY = "components_only"
    SCRIPTS_ONLY = "scripts_only"
    DOCUMENTATION_ONLY = "documentation_only"
    CONFIGURATION_ONLY = "configuration_only"
    CUSTOM_SCOPE = "custom_scope"


class ResultRanking(Enum):
    """Result ranking method"""
    RELEVANCE = "relevance"
    RECENCY = "recency"
    POPULARITY = "popularity"
    COMPLEXITY = "complexity"
    CUSTOM = "custom"


@dataclass
class SearchIndex:
    """Search index entry"""
    id: str
    type: str  # component, script, file, function, class
    name: str
    file_path: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    last_modified: datetime = field(default_factory=datetime.now)
    size: int = 0
    language: str = "python"
    searchable_text: str = ""
    semantic_vector: Optional[List[float]] = None
    popularity_score: float = 0.0
    access_count: int = 0
    search_tokens: List[str] = field(default_factory=list)


@dataclass
class SearchQuery:
    """Search query structure"""
    query: str
    search_type: SearchType = SearchType.FULL_TEXT
    scope: SearchScope = SearchScope.ENTIRE_CODEBASE
    filters: Dict[str, Any] = field(default_factory=dict)
    ranking: ResultRanking = ResultRanking.RELEVANCE
    limit: int = 20
    offset: int = 0
    include_content: bool = False
    highlight_matches: bool = True
    fuzzy_search: bool = True
    boost_recent: bool = False
    exclude_patterns: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """Search result entry"""
    id: str
    type: str
    name: str
    file_path: str
    content_snippet: str
    relevance_score: float
    match_positions: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    last_modified: datetime = field(default_factory=datetime.now)
    size: int = 0


@dataclass
class SearchAnalytics:
    """Search analytics data"""
    query: str
    timestamp: datetime
    results_count: int
    execution_time: float
    search_type: SearchType
    scope: SearchScope
    filters_used: List[str]
    clicked_results: List[str] = field(default_factory=list)
    user_id: Optional[str] = None
    session_id: Optional[str] = None


class SearchableCodebaseIndex:
    """Advanced searchable codebase index"""
    
    def __init__(self):
        self.index: Dict[str, SearchIndex] = {}
        self.search_analytics: List[SearchAnalytics] = []
        self.search_history: List[SearchQuery] = []
        
        # Search configuration
        self.config = {
            'min_token_length': 2,
            'max_token_length': 50,
            'stop_words': {
                'python': ['and', 'or', 'the', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'shall'],
                'general': ['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did']
            },
            'fuzzy_threshold': 0.8,
            'semantic_threshold': 0.7,
            'boost_recent_days': 30,
            'max_results': 1000
        }
        
        # Inverted index for fast searching
        self.inverted_index: Dict[str, List[str]] = defaultdict(list)
        self.type_index: Dict[str, List[str]] = defaultdict(list)
        self.tag_index: Dict[str, List[str]] = defaultdict(list)
        self.dependency_index: Dict[str, List[str]] = defaultdict(list)
        
        # Search statistics
        self.search_stats = {
            'total_searches': 0,
            'average_results': 0.0,
            'average_execution_time': 0.0,
            'popular_queries': Counter(),
            'search_types': Counter(),
            'search_scopes': Counter()
        }
        
        # Initialize index
        self._initialize_index()
    
    def _initialize_index(self):
        """Initialize the search index"""
        try:
            # Create index directories
            self.index_dir = Path("c:\\Users\\Administrator\\Jarvis\\docs\\search_index")
            self.index_dir.mkdir(parents=True, exist_ok=True)
            
            logger.info("Searchable codebase index initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize search index: {e}")
    
    async def build_index(self, components: Dict[str, Any], scripts: Dict[str, Any]):
        """Build search index from components and scripts"""
        try:
            logger.info("Building search index...")
            
            # Clear existing index
            self.index.clear()
            self.inverted_index.clear()
            self.type_index.clear()
            self.tag_index.clear()
            self.dependency_index.clear()
            
            # Index components
            for component_id, component_data in components.items():
                await self._index_component(component_id, component_data)
            
            # Index scripts
            for script_id, script_data in scripts.items():
                await self._index_script(script_id, script_data)
            
            # Build inverted index
            await self._build_inverted_index()
            
            # Save index
            await self._save_index()
            
            logger.info(f"Search index built: {len(self.index)} items indexed")
            
        except Exception as e:
            logger.error(f"Failed to build search index: {e}")
    
    async def _index_component(self, component_id: str, component_data: Dict[str, Any]):
        """Index a component"""
        try:
            # Read file content
            file_path = Path("c:\\Users\\Administrator\\Jarvis") / component_data['file_path']
            
            if not file_path.exists():
                return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create search index entry
            index_entry = SearchIndex(
                id=component_id,
                type='component',
                name=component_data['name'],
                file_path=component_data['file_path'],
                content=content,
                metadata={
                    'type': component_data['type'],
                    'functions': component_data.get('functions', []),
                    'classes': component_data.get('classes', []),
                    'imports': component_data.get('imports', []),
                    'lines_of_code': component_data.get('lines_of_code', 0),
                    'complexity_score': component_data.get('complexity_score', 0)
                },
                tags=component_data.get('tags', []),
                dependencies=component_data.get('imports', []),
                last_modified=datetime.fromisoformat(component_data['last_modified']) if 'last_modified' in component_data else datetime.now(),
                size=len(content),
                language='python'
            )
            
            # Generate searchable text
            index_entry.searchable_text = self._generate_searchable_text(index_entry)
            
            # Generate search tokens
            index_entry.search_tokens = self._tokenize_text(index_entry.searchable_text)
            
            # Calculate popularity score
            index_entry.popularity_score = self._calculate_popularity_score(index_entry)
            
            self.index[component_id] = index_entry
            
        except Exception as e:
            logger.error(f"Failed to index component {component_id}: {e}")
    
    async def _index_script(self, script_id: str, script_data: Dict[str, Any]):
        """Index a script"""
        try:
            # Read file content
            file_path = Path("c:\\Users\\Administrator\\Jarvis") / script_data['file_path']
            
            if not file_path.exists():
                return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create search index entry
            index_entry = SearchIndex(
                id=script_id,
                type='script',
                name=script_data['name'],
                file_path=script_data['file_path'],
                content=content,
                metadata={
                    'type': script_data['type'],
                    'purpose': script_data.get('purpose', ''),
                    'dependencies': script_data.get('dependencies', []),
                    'usage_count': script_data.get('usage_count', 0),
                    'success_rate': script_data.get('success_rate', 0.0),
                    'execution_time': script_data.get('execution_time', 0.0)
                },
                tags=script_data.get('tags', []),
                dependencies=script_data.get('dependencies', []),
                last_modified=datetime.fromisoformat(script_data['created_at']) if 'created_at' in script_data else datetime.now(),
                size=len(content),
                language='python'
            )
            
            # Generate searchable text
            index_entry.searchable_text = self._generate_searchable_text(index_entry)
            
            # Generate search tokens
            index_entry.search_tokens = self._tokenize_text(index_entry.searchable_text)
            
            # Calculate popularity score
            index_entry.popularity_score = self._calculate_popularity_score(index_entry)
            
            self.index[script_id] = index_entry
            
        except Exception as e:
            logger.error(f"Failed to index script {script_id}: {e}")
    
    def _generate_searchable_text(self, index_entry: SearchIndex) -> str:
        """Generate searchable text from index entry"""
        searchable_parts = []
        
        # Add name
        searchable_parts.append(index_entry.name)
        
        # Add content (first 1000 chars)
        content_preview = index_entry.content[:1000]
        searchable_parts.append(content_preview)
        
        # Add metadata
        if index_entry.metadata:
            for key, value in index_entry.metadata.items():
                if isinstance(value, str):
                    searchable_parts.append(value)
                elif isinstance(value, list):
                    searchable_parts.extend(str(v) for v in value)
        
        # Add tags
        searchable_parts.extend(index_entry.tags)
        
        # Add dependencies
        searchable_parts.extend(index_entry.dependencies)
        
        # Add file path
        searchable_parts.append(index_entry.file_path)
        
        return ' '.join(searchable_parts)
    
    def _tokenize_text(self, text: str) -> List[str]:
        """Tokenize text for searching"""
        # Convert to lowercase
        text = text.lower()
        
        # Split on whitespace and punctuation
        tokens = re.findall(r'\b\w+\b', text)
        
        # Filter tokens
        filtered_tokens = []
        for token in tokens:
            # Length filter
            if len(token) < self.config['min_token_length'] or len(token) > self.config['max_token_length']:
                continue
            
            # Stop words filter
            if token in self.config['stop_words']['general'] or token in self.config['stop_words']['python']:
                continue
            
            filtered_tokens.append(token)
        
        return list(set(filtered_tokens))  # Remove duplicates
    
    def _calculate_popularity_score(self, index_entry: SearchIndex) -> float:
        """Calculate popularity score for ranking"""
        score = 0.0
        
        # Base score
        score += 0.1
        
        # Size score (larger files get slightly higher score)
        if index_entry.size > 0:
            score += min(0.2, math.log10(index_entry.size) / 10)
        
        # Metadata score
        if index_entry.metadata:
            # Functions/classes count
            functions = len(index_entry.metadata.get('functions', []))
            classes = len(index_entry.metadata.get('classes', []))
            score += min(0.2, (functions + classes) * 0.01)
            
            # Usage count for scripts
            usage_count = index_entry.metadata.get('usage_count', 0)
            score += min(0.3, usage_count * 0.01)
        
        # Tag score
        score += min(0.2, len(index_entry.tags) * 0.05)
        
        # Dependency score
        score += min(0.2, len(index_entry.dependencies) * 0.01)
        
        return min(1.0, score)
    
    async def _build_inverted_index(self):
        """Build inverted index for fast searching"""
        for item_id, index_entry in self.index.items():
            # Type index
            self.type_index[index_entry.type].append(item_id)
            
            # Tag index
            for tag in index_entry.tags:
                self.tag_index[tag].append(item_id)
            
            # Dependency index
            for dep in index_entry.dependencies:
                self.dependency_index[dep].append(item_id)
            
            # Token index (inverted index)
            for token in index_entry.search_tokens:
                self.inverted_index[token].append(item_id)
    
    async def _save_index(self):
        """Save search index to disk"""
        try:
            # Save main index
            index_data = {}
            for item_id, index_entry in self.index.items():
                index_data[item_id] = {
                    'id': index_entry.id,
                    'type': index_entry.type,
                    'name': index_entry.name,
                    'file_path': index_entry.file_path,
                    'content': index_entry.content[:1000],  # Only save preview
                    'metadata': index_entry.metadata,
                    'tags': index_entry.tags,
                    'dependencies': index_entry.dependencies,
                    'last_modified': index_entry.last_modified.isoformat(),
                    'size': index_entry.size,
                    'language': index_entry.language,
                    'searchable_text': index_entry.searchable_text,
                    'search_tokens': index_entry.search_tokens,
                    'popularity_score': index_entry.popularity_score,
                    'access_count': index_entry.access_count
                }
            
            with open(self.index_dir / 'search_index.json', 'w') as f:
                json.dump(index_data, f, indent=2)
            
            # Save inverted index
            inverted_data = dict(self.inverted_index)
            with open(self.index_dir / 'inverted_index.json', 'w') as f:
                json.dump(inverted_data, f, indent=2)
            
            # Save type index
            type_data = dict(self.type_index)
            with open(self.index_dir / 'type_index.json', 'w') as f:
                json.dump(type_data, f, indent=2)
            
            # Save tag index
            tag_data = dict(self.tag_index)
            with open(self.index_dir / 'tag_index.json', 'w') as f:
                json.dump(tag_data, f, indent=2)
            
            # Save dependency index
            dep_data = dict(self.dependency_index)
            with open(self.index_dir / 'dependency_index.json', 'w') as f:
                json.dump(dep_data, f, indent=2)
            
            # Save search statistics
            with open(self.index_dir / 'search_stats.json', 'w') as f:
                json.dump(self.search_stats, f, indent=2)
            
            logger.info("Search index saved to disk")
            
        except Exception as e:
            logger.error(f"Failed to save search index: {e}")
    
    async def search(self, query: SearchQuery) -> Dict[str, Any]:
        """Perform search query"""
        try:
            start_time = datetime.now()
            
            # Record search query
            self.search_history.append(query)
            
            # Perform search based on type
            if query.search_type == SearchType.FULL_TEXT:
                results = await self._full_text_search(query)
            elif query.search_type == SearchType.SEMANTIC:
                results = await self._semantic_search(query)
            elif query.search_type == SearchType.PATTERN:
                results = await self._pattern_search(query)
            elif query.search_type == SearchType.DEPENDENCY:
                results = await self._dependency_search(query)
            elif query.search_type == SearchType.STRUCTURAL:
                results = await self._structural_search(query)
            elif query.search_type == SearchType.METADATA:
                results = await self._metadata_search(query)
            else:  # HYBRID
                results = await self._hybrid_search(query)
            
            # Apply filters
            filtered_results = await self._apply_filters(results, query.filters)
            
            # Apply ranking
            ranked_results = await self._apply_ranking(filtered_results, query.ranking)
            
            # Apply pagination
            paginated_results = ranked_results[query.offset:query.offset + query.limit]
            
            # Generate content snippets if requested
            if query.include_content:
                for result in paginated_results:
                    result['content_snippet'] = self._generate_content_snippet(
                        self.index[result['id']], 
                        query.query
                    )
            
            # Generate match highlights if requested
            if query.highlight_matches:
                for result in paginated_results:
                    result['match_positions'] = self._generate_match_positions(
                        self.index[result['id']], 
                        query.query
                    )
            
            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Record analytics
            analytics = SearchAnalytics(
                query=query.query,
                timestamp=start_time,
                results_count=len(ranked_results),
                execution_time=execution_time,
                search_type=query.search_type,
                scope=query.scope,
                filters_used=list(query.filters.keys())
            )
            self.search_analytics.append(analytics)
            
            # Update search statistics
            self._update_search_stats(analytics)
            
            # Update access counts
            for result in paginated_results:
                if result['id'] in self.index:
                    self.index[result['id']].access_count += 1
            
            return {
                'query': query.query,
                'search_type': query.search_type.value,
                'scope': query.scope.value,
                'results': paginated_results,
                'total_results': len(ranked_results),
                'execution_time': execution_time,
                'filters_applied': list(query.filters.keys()),
                'ranking_method': query.ranking.value
            }
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {
                'query': query.query,
                'error': str(e),
                'results': [],
                'total_results': 0,
                'execution_time': 0.0
            }
    
    async def _full_text_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform full-text search"""
        try:
            # Tokenize query
            query_tokens = self._tokenize_text(query.query)
            
            if not query_tokens:
                return []
            
            # Find matching items
            matching_items = set()
            token_matches = {}
            
            for token in query_tokens:
                # Exact matches
                if token in self.inverted_index:
                    for item_id in self.inverted_index[token]:
                        matching_items.add(item_id)
                        token_matches.setdefault(item_id, 0)
                        token_matches[item_id] += 1
                
                # Fuzzy matches
                if query.fuzzy_search:
                    fuzzy_matches = await self._fuzzy_match_token(token)
                    for item_id, score in fuzzy_matches:
                        if score >= self.config['fuzzy_threshold']:
                            matching_items.add(item_id)
                            token_matches.setdefault(item_id, 0)
                            token_matches[item_id] += score
            
            # Generate results
            results = []
            for item_id in matching_items:
                index_entry = self.index[item_id]
                
                # Calculate relevance score
                relevance_score = token_matches.get(item_id, 0) / len(query_tokens)
                
                # Apply recent boost if requested
                if query.boost_recent:
                    days_old = (datetime.now() - index_entry.last_modified).days
                    if days_old <= self.config['boost_recent_days']:
                        relevance_score *= 1.5
                
                result = {
                    'id': item_id,
                    'type': index_entry.type,
                    'name': index_entry.name,
                    'file_path': index_entry.file_path,
                    'relevance_score': relevance_score,
                    'last_modified': index_entry.last_modified,
                    'size': index_entry.size,
                    'tags': index_entry.tags,
                    'metadata': index_entry.metadata
                }
                
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Full-text search failed: {e}")
            return []
    
    async def _semantic_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform semantic search"""
        try:
            # This would integrate with semantic search models
            # For now, fall back to full-text search
            return await self._full_text_search(query)
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    async def _pattern_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform pattern-based search"""
        try:
            # Convert query to regex pattern
            pattern = re.compile(query.query, re.IGNORECASE)
            
            results = []
            for item_id, index_entry in self.index.items():
                # Search in content
                if pattern.search(index_entry.content):
                    matches = len(pattern.findall(index_entry.content))
                    relevance_score = min(1.0, matches / 10.0)
                    
                    result = {
                        'id': item_id,
                        'type': index_entry.type,
                        'name': index_entry.name,
                        'file_path': index_entry.file_path,
                        'relevance_score': relevance_score,
                        'last_modified': index_entry.last_modified,
                        'size': index_entry.size,
                        'tags': index_entry.tags,
                        'metadata': index_entry.metadata
                    }
                    
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Pattern search failed: {e}")
            return []
    
    async def _dependency_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform dependency-based search"""
        try:
            # Search in dependency index
            matching_items = self.dependency_index.get(query.query.lower(), [])
            
            results = []
            for item_id in matching_items:
                index_entry = self.index[item_id]
                
                result = {
                    'id': item_id,
                    'type': index_entry.type,
                    'name': index_entry.name,
                    'file_path': index_entry.file_path,
                    'relevance_score': 0.8,  # Fixed score for dependency matches
                    'last_modified': index_entry.last_modified,
                    'size': index_entry.size,
                    'tags': index_entry.tags,
                    'metadata': index_entry.metadata
                }
                
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Dependency search failed: {e}")
            return []
    
    async def _structural_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform structural search"""
        try:
            # This would analyze code structure
            # For now, fall back to full-text search
            return await self._full_text_search(query)
            
        except Exception as e:
            logger.error(f"Structural search failed: {e}")
            return []
    
    async def _metadata_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform metadata search"""
        try:
            results = []
            query_lower = query.query.lower()
            
            for item_id, index_entry in self.index.items():
                # Search in metadata
                metadata_matches = 0
                for key, value in index_entry.metadata.items():
                    if isinstance(value, str) and query_lower in value.lower():
                        metadata_matches += 1
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, str) and query_lower in item.lower():
                                metadata_matches += 1
                
                # Search in tags
                tag_matches = sum(1 for tag in index_entry.tags if query_lower in tag.lower())
                
                total_matches = metadata_matches + tag_matches
                
                if total_matches > 0:
                    relevance_score = min(1.0, total_matches / 5.0)
                    
                    result = {
                        'id': item_id,
                        'type': index_entry.type,
                        'name': index_entry.name,
                        'file_path': index_entry.file_path,
                        'relevance_score': relevance_score,
                        'last_modified': index_entry.last_modified,
                        'size': index_entry.size,
                        'tags': index_entry.tags,
                        'metadata': index_entry.metadata
                    }
                    
                    results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Metadata search failed: {e}")
            return []
    
    async def _hybrid_search(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """Perform hybrid search combining multiple methods"""
        try:
            # Combine results from different search methods
            all_results = []
            
            # Full-text search
            ft_results = await self._full_text_search(query)
            all_results.extend(ft_results)
            
            # Metadata search
            md_results = await self._metadata_search(query)
            all_results.extend(md_results)
            
            # Dependency search
            dep_results = await self._dependency_search(query)
            all_results.extend(dep_results)
            
            # Merge and deduplicate results
            merged_results = {}
            for result in all_results:
                item_id = result['id']
                if item_id in merged_results:
                    # Combine scores
                    merged_results[item_id]['relevance_score'] = max(
                        merged_results[item_id]['relevance_score'],
                        result['relevance_score']
                    )
                else:
                    merged_results[item_id] = result
            
            return list(merged_results.values())
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []
    
    async def _fuzzy_match_token(self, token: str) -> Dict[str, float]:
        """Perform fuzzy matching for token"""
        try:
            fuzzy_matches = {}
            
            for indexed_token in self.inverted_index.keys():
                # Calculate Levenshtein distance (simplified)
                distance = self._levenshtein_distance(token, indexed_token)
                max_len = max(len(token), len(indexed_token))
                
                if max_len > 0:
                    similarity = 1.0 - (distance / max_len)
                    if similarity >= self.config['fuzzy_threshold']:
                        for item_id in self.inverted_index[indexed_token]:
                            fuzzy_matches[item_id] = max(
                                fuzzy_matches.get(item_id, 0),
                                similarity
                            )
            
            return fuzzy_matches
            
        except Exception as e:
            logger.error(f"Fuzzy matching failed: {e}")
            return {}
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    async def _apply_filters(self, results: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Apply filters to search results"""
        try:
            if not filters:
                return results
            
            filtered_results = []
            
            for result in results:
                item_id = result['id']
                index_entry = self.index[item_id]
                
                # Apply each filter
                passes_filters = True
                
                # Type filter
                if 'type' in filters:
                    if isinstance(filters['type'], list):
                        if result['type'] not in filters['type']:
                            passes_filters = False
                    else:
                        if result['type'] != filters['type']:
                            passes_filters = False
                
                # Tag filter
                if 'tags' in filters:
                    required_tags = filters['tags']
                    if isinstance(required_tags, list):
                        if not any(tag in index_entry.tags for tag in required_tags):
                            passes_filters = False
                    else:
                        if required_tags not in index_entry.tags:
                            passes_filters = False
                
                # Date range filter
                if 'date_from' in filters:
                    date_from = datetime.fromisoformat(filters['date_from'])
                    if index_entry.last_modified < date_from:
                        passes_filters = False
                
                if 'date_to' in filters:
                    date_to = datetime.fromisoformat(filters['date_to'])
                    if index_entry.last_modified > date_to:
                        passes_filters = False
                
                # Size filter
                if 'min_size' in filters:
                    if index_entry.size < filters['min_size']:
                        passes_filters = False
                
                if 'max_size' in filters:
                    if index_entry.size > filters['max_size']:
                        passes_filters = False
                
                # Language filter
                if 'language' in filters:
                    if index_entry.language != filters['language']:
                        passes_filters = False
                
                if passes_filters:
                    filtered_results.append(result)
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Failed to apply filters: {e}")
            return results
    
    async def _apply_ranking(self, results: List[Dict[str, Any]], ranking: ResultRanking) -> List[Dict[str, Any]]:
        """Apply ranking to search results"""
        try:
            if ranking == ResultRanking.RELEVANCE:
                # Already sorted by relevance
                return sorted(results, key=lambda x: x['relevance_score'], reverse=True)
            
            elif ranking == ResultRanking.RECENCY:
                return sorted(results, key=lambda x: x['last_modified'], reverse=True)
            
            elif ranking == ResultRanking.POPULARITY:
                return sorted(results, key=lambda x: self.index[x['id']].popularity_score, reverse=True)
            
            elif ranking == ResultRanking.COMPLEXITY:
                return sorted(results, key=lambda x: self.index[x['id']].metadata.get('complexity_score', 0), reverse=True)
            
            else:
                return results
                
        except Exception as e:
            logger.error(f"Failed to apply ranking: {e}")
            return results
    
    def _generate_content_snippet(self, index_entry: SearchIndex, query: str) -> str:
        """Generate content snippet with query highlighting"""
        try:
            content = index_entry.content
            query_lower = query.lower()
            
            # Find first occurrence
            pos = content.lower().find(query_lower)
            if pos == -1:
                return content[:200] + "..." if len(content) > 200 else content
            
            # Extract snippet around match
            start = max(0, pos - 50)
            end = min(len(content), pos + 150)
            
            snippet = content[start:end]
            
            # Add ellipsis if truncated
            if start > 0:
                snippet = "..." + snippet
            if end < len(content):
                snippet = snippet + "..."
            
            return snippet
            
        except Exception as e:
            logger.error(f"Failed to generate content snippet: {e}")
            return ""
    
    def _generate_match_positions(self, index_entry: SearchIndex, query: str) -> List[Dict[str, Any]]:
        """Generate match positions for highlighting"""
        try:
            positions = []
            content = index_entry.content
            query_lower = query.lower()
            
            # Find all occurrences
            pos = content.lower().find(query_lower)
            while pos != -1:
                positions.append({
                    'start': pos,
                    'end': pos + len(query),
                    'text': content[pos:pos + len(query)]
                })
                pos = content.lower().find(query_lower, pos + 1)
            
            return positions
            
        except Exception as e:
            logger.error(f"Failed to generate match positions: {e}")
            return []
    
    def _update_search_stats(self, analytics: SearchAnalytics):
        """Update search statistics"""
        try:
            self.search_stats['total_searches'] += 1
            
            # Update average results
            total_searches = self.search_stats['total_searches']
            current_avg = self.search_stats['average_results']
            self.search_stats['average_results'] = ((current_avg * (total_searches - 1)) + analytics.results_count) / total_searches
            
            # Update average execution time
            current_time_avg = self.search_stats['average_execution_time']
            self.search_stats['average_execution_time'] = ((current_time_avg * (total_searches - 1)) + analytics.execution_time) / total_searches
            
            # Update popular queries
            self.search_stats['popular_queries'][analytics.query] += 1
            
            # Update search types
            self.search_stats['search_types'][analytics.search_type.value] += 1
            
            # Update search scopes
            self.search_stats['search_scopes'][analytics.scope.value] += 1
            
        except Exception as e:
            logger.error(f"Failed to update search stats: {e}")
    
    def get_search_suggestions(self, query: str, limit: int = 10) -> List[str]:
        """Get search suggestions based on query"""
        try:
            suggestions = []
            query_lower = query.lower()
            
            # Get popular queries that start with query
            for popular_query, count in self.search_stats['popular_queries'].most_common():
                if popular_query.lower().startswith(query_lower):
                    suggestions.append(popular_query)
                    if len(suggestions) >= limit:
                        break
            
            # Add token suggestions from index
            for token in self.inverted_index.keys():
                if token.startswith(query_lower) and token not in suggestions:
                    suggestions.append(token)
                    if len(suggestions) >= limit:
                        break
            
            return suggestions[:limit]
            
        except Exception as e:
            logger.error(f"Failed to get search suggestions: {e}")
            return []
    
    def get_search_analytics(self, days: int = 30) -> Dict[str, Any]:
        """Get search analytics"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # Filter analytics by date
            recent_analytics = [
                analytics for analytics in self.search_analytics
                if analytics.timestamp >= cutoff_date
            ]
            
            # Calculate statistics
            total_searches = len(recent_analytics)
            average_results = sum(a.results_count for a in recent_analytics) / total_searches if total_searches > 0 else 0
            average_execution_time = sum(a.execution_time for a in recent_analytics) / total_searches if total_searches > 0 else 0
            
            # Popular queries
            popular_queries = Counter(a.query for a in recent_analytics).most_common(10)
            
            # Search types distribution
            search_types = Counter(a.search_type.value for a in recent_analytics)
            
            # Search scopes distribution
            search_scopes = Counter(a.scope.value for a in recent_analytics)
            
            # Daily search volume
            daily_volume = defaultdict(int)
            for analytics in recent_analytics:
                date_key = analytics.timestamp.date().isoformat()
                daily_volume[date_key] += 1
            
            return {
                'period_days': days,
                'total_searches': total_searches,
                'average_results': average_results,
                'average_execution_time': average_execution_time,
                'popular_queries': dict(popular_queries),
                'search_types': dict(search_types),
                'search_scopes': dict(search_scopes),
                'daily_volume': dict(daily_volume)
            }
            
        except Exception as e:
            logger.error(f"Failed to get search analytics: {e}")
            return {}


# Global instance
_searchable_index = None


def get_searchable_codebase_index() -> SearchableCodebaseIndex:
    """Get global searchable codebase index instance"""
    global _searchable_index
    if _searchable_index is None:
        _searchable_index = SearchableCodebaseIndex()
    return _searchable_index
