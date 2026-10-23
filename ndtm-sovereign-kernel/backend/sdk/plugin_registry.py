import importlib
import inspect
import pkgutil
from typing import Dict, List, Type, Any
from sdk.interfaces import DatasetAdapter, DSLRulePlugin, RoutingPolicyPlugin
from core.logging_otel import logger


class PluginRegistry:
    """Thread-safe centralized registry for all NDTM plugins with auto-discovery."""

    _adapters: Dict[str, DatasetAdapter] = {}
    _dsl_rules: Dict[str, DSLRulePlugin] = {}
    _routing_policies: Dict[str, RoutingPolicyPlugin] = {}

    @classmethod
    def register_adapter(cls, adapter: DatasetAdapter) -> None:
        cls._adapters[adapter.source_identifier] = adapter
        logger.info("plugin_registered", plugin_type="DatasetAdapter", identifier=adapter.source_identifier)

    @classmethod
    def register_rule(cls, rule: DSLRulePlugin) -> None:
        cls._dsl_rules[rule.rule_name] = rule
        logger.info("plugin_registered", plugin_type="DSLRulePlugin", identifier=rule.rule_name)

    @classmethod
    def register_policy(cls, policy: RoutingPolicyPlugin) -> None:
        cls._routing_policies[policy.policy_name] = policy
        logger.info("plugin_registered", plugin_type="RoutingPolicyPlugin", identifier=policy.policy_name)

    @classmethod
    def get_adapter(cls, identifier: str) -> DatasetAdapter:
        if identifier not in cls._adapters:
            raise KeyError(f"No DatasetAdapter registered for identifier: {identifier}")
        return cls._adapters[identifier]

    @classmethod
    def get_all_adapters(cls) -> Dict[str, DatasetAdapter]:
        return dict(cls._adapters)

    @classmethod
    def get_rule(cls, rule_name: str) -> DSLRulePlugin:
        if rule_name not in cls._dsl_rules:
            raise KeyError(f"No DSLRulePlugin registered for name: {rule_name}")
        return cls._dsl_rules[rule_name]

    @classmethod
    def get_all_rules(cls) -> List[DSLRulePlugin]:
        # Return sorted by priority descending
        return sorted(cls._dsl_rules.values(), key=lambda r: r.priority, reverse=True)

    @classmethod
    def get_policy(cls, policy_name: str) -> RoutingPolicyPlugin:
        if policy_name not in cls._routing_policies:
            raise KeyError(f"No RoutingPolicyPlugin registered for name: {policy_name}")
        return cls._routing_policies[policy_name]

    @classmethod
    def discover_plugins(cls, package_name: str = "plugins") -> None:
        """Dynamically discovers and imports all plugin modules in package."""
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            logger.warning("plugin_package_not_found", package=package_name)
            return

        prefix = package.__name__ + "."
        for _, module_name, _ in pkgutil.iter_modules(package.__path__, prefix):
            try:
                mod = importlib.import_module(module_name)
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name)
                    if inspect.isclass(attr) and not inspect.isabstract(attr):
                        if issubclass(attr, DatasetAdapter) and attr is not DatasetAdapter:
                            cls.register_adapter(attr())
                        elif issubclass(attr, DSLRulePlugin) and attr is not DSLRulePlugin:
                            cls.register_rule(attr())
                        elif issubclass(attr, RoutingPolicyPlugin) and attr is not RoutingPolicyPlugin:
                            cls.register_policy(attr())
            except Exception as e:
                logger.error("plugin_discovery_failed", module=module_name, error=str(e))
