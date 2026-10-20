#!/usr/bin/env python3
"""Exercise JVM quality guidance in disposable Maven fixtures, never a user project.

Resolve versions explicitly once, then use that project-owned JSON for reruns.
No tool release numbers are embedded here or in the distributed skills.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

CENTRAL = 'https://repo.maven.apache.org/maven2/'
ARTIFACTS = {
    'maven': 'org.apache.maven:apache-maven',
    'wrapper': 'org.apache.maven.plugins:maven-wrapper-plugin',
    'compiler': 'org.apache.maven.plugins:maven-compiler-plugin',
    'clean': 'org.apache.maven.plugins:maven-clean-plugin',
    'resources': 'org.apache.maven.plugins:maven-resources-plugin',
    'jar': 'org.apache.maven.plugins:maven-jar-plugin',
    'help': 'org.apache.maven.plugins:maven-help-plugin',
    'surefire': 'org.apache.maven.plugins:maven-surefire-plugin',
    'failsafe': 'org.apache.maven.plugins:maven-failsafe-plugin',
    'jacoco': 'org.jacoco:jacoco-maven-plugin',
    'enforcer': 'org.apache.maven.plugins:maven-enforcer-plugin',
    'antrun': 'org.apache.maven.plugins:maven-antrun-plugin',
    'spotless': 'com.diffplug.spotless:spotless-maven-plugin',
    'formatter': 'com.google.googlejavaformat:google-java-format',
    'checkstyle_plugin': 'org.apache.maven.plugins:maven-checkstyle-plugin',
    'checkstyle': 'com.puppycrawl.tools:checkstyle',
    'spotbugs': 'com.github.spotbugs:spotbugs-maven-plugin',
    'findsecbugs': 'com.h3xstream.findsecbugs:findsecbugs-plugin',
    'pmd': 'org.apache.maven.plugins:maven-pmd-plugin',
    'errorprone': 'com.google.errorprone:error_prone_core',
    'kotlin': 'org.jetbrains.kotlin:kotlin-maven-plugin',
    'ktlint': 'com.pinterest.ktlint:ktlint-cli',
    'detekt': 'io.gitlab.arturbosch.detekt:detekt-cli',
    'junit': 'org.junit.jupiter:junit-jupiter',
}
MODULES = ('java-only', 'kotlin-only', 'mixed')
NS = {'m': 'http://maven.apache.org/POM/4.0.0'}


def resolve_versions(path):
    def resolve(item):
        key, coordinate = item
        group, artifact = coordinate.split(':')
        url = CENTRAL + group.replace('.', '/') + '/' + artifact + '/maven-metadata.xml'
        with urllib.request.urlopen(url, timeout=30) as response:
            tree = ET.fromstring(response.read())
        # Preview releases are not selected, even if metadata calls one "release".
        versions = [v.text for v in tree.findall('./versioning/versions/version')
                    if re.fullmatch(r'\d+(?:\.\d+)+', v.text or '')]
        if not versions:
            raise ValueError('No stable numeric releases for ' + coordinate)
        return key, max(versions, key=lambda v: tuple(map(int, v.split('.'))))
    with ThreadPoolExecutor(max_workers=8) as pool:
        versions = dict(pool.map(resolve, ARTIFACTS.items()))
    path.write_text(json.dumps({'resolved_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                                'source': CENTRAL, 'versions': versions}, indent=2) + '\n')
    print('Resolved candidate pins to ' + str(path), flush=True)
    print('Check official release notes/compatibility before treating candidates as supported.', flush=True)


def plugin(key, body=''):
    group, artifact = ARTIFACTS[key].split(':')
    return f'<plugin><groupId>{group}</groupId><artifactId>{artifact}</artifactId><version>${{{key}.version}}</version>{body}</plugin>'


def execution(name, phase, goals, config=''):
    return f'<execution><id>{name}</id><phase>{phase}</phase><goals>' + ''.join(f'<goal>{g}</goal>' for g in goals) + f'</goals>{config}</execution>'


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def create_fixture(root, versions):
    # A second real javaagent proves coverage attachment preserves existing agents.
    source = write(root, 'agent/SentinelAgent.java', 'public class SentinelAgent { public static void premain(String args) { System.setProperty("quality.agent", "active"); } }\n')
    subprocess.run(['javac', '--release', '17', str(source)], check=True, capture_output=True)
    manifest = write(root, 'agent/MANIFEST.MF', 'Premain-Class: SentinelAgent\n\n')
    subprocess.run(['jar', 'cfm', str(root/'sentinel-agent.jar'), str(manifest), '-C', str(root/'agent'), 'SentinelAgent.class'], check=True, capture_output=True)
    properties = ''.join(f'<{k}.version>{v}</{k}.version>' for k, v in versions.items())
    properties += '''<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <maven.compiler.release>17</maven.compiler.release><coverage.unit.args/>
    <coverage.it.args/><coverage.child.args/><coverage.required>false</coverage.required>
    <test.jvm.args>-javaagent:${fixture.root}/sentinel-agent.jar -Dquality.sentinel=preserved</test.jvm.args>
    <fixture.root>${maven.multiModuleProjectDirectory}</fixture.root>'''
    compiler = plugin('compiler', '''<configuration><release>${maven.compiler.release}</release>
      <showWarnings>true</showWarnings><failOnWarning>true</failOnWarning>
      <compilerArgs><arg>-Xlint:deprecation</arg></compilerArgs></configuration>''')
    unit = plugin('surefire', '''<configuration><argLine>@{coverage.unit.args} ${test.jvm.args}</argLine>
      <failIfNoTests>true</failIfNoTests></configuration>''')
    integration = plugin('failsafe', '''<configuration><argLine>@{coverage.it.args} ${test.jvm.args} "-Dquality.child.agent=@{coverage.child.args}"</argLine>
      <failIfNoTests>true</failIfNoTests></configuration><executions>''' +
      execution('integration', 'integration-test', ['integration-test']) +
      execution('integration-results', 'verify', ['verify']) + '</executions>')
    enforcer = plugin('enforcer', '<executions>' + execution('tools', 'validate', ['enforce'], '''<configuration>
      <rules><requireMavenVersion><version>[3,4)</version></requireMavenVersion>
      <requireJavaVersion><version>[25,26)</version></requireJavaVersion>
      <banDuplicatePomDependencyVersions/></rules></configuration>''') + '</executions>')
    jacoco = plugin('jacoco', '<executions>' +
      execution('unit-agent', 'initialize', ['prepare-agent'], '''<configuration>
      <propertyName>coverage.unit.args</propertyName><destFile>${project.build.directory}/unit.exec</destFile></configuration>''') +
      execution('it-agent', 'pre-integration-test', ['prepare-agent'], '''<configuration>
      <propertyName>coverage.it.args</propertyName><destFile>${project.build.directory}/it.exec</destFile></configuration>''') +
      execution('merge-coverage', 'post-integration-test', ['merge'], '''<configuration>
      <fileSets><fileSet><directory>${project.build.directory}</directory><includes><include>unit.exec</include><include>it.exec</include><include>child.exec</include></includes></fileSet></fileSets>
      <destFile>${project.build.directory}/combined.exec</destFile></configuration>''') +
      execution('coverage-report', 'post-integration-test', ['report'], '''<configuration>
      <dataFile>${project.build.directory}/combined.exec</dataFile></configuration>''') +
      execution('coverage-floor', 'verify', ['check'], '''<configuration>
      <dataFile>${project.build.directory}/combined.exec</dataFile><rules><rule><element>BUNDLE</element><limits>
      <limit><counter>LINE</counter><value>COVEREDRATIO</value><minimum>0.90</minimum></limit>
      <limit><counter>BRANCH</counter><value>COVEREDRATIO</value><minimum>1.00</minimum></limit>
      </limits></rule></rules></configuration>''') + '</executions>')
    reset = '<target><delete><fileset dir="${project.build.directory}" erroronmissingdir="false"><include name="*.exec"/><include name="site/jacoco/**"/></fileset></delete></target>'
    guard = '<target>'
    for filename in ('unit.exec', 'it.exec', 'site/jacoco/jacoco.xml'):
        guard += f'''<fail message="Required coverage data missing or empty: {filename}"><condition><not><and>
        <available file="${{project.build.directory}}/{filename}"/>
        <length file="${{project.build.directory}}/{filename}" length="0" when="greater"/>
        </and></not></condition></fail>'''
    guard += '\n<fail message="Required child coverage data missing or empty"><condition><and><equals arg1="${project.artifactId}" arg2="java-only"/><not><and><available file="${project.build.directory}/child.exec"/><length file="${project.build.directory}/child.exec" length="0" when="greater"/></and></not></and></condition></fail>'
    guard += '<loadfile property="coverage.xml" srcfile="${project.build.directory}/site/jacoco/jacoco.xml"/><fail message="Expected production class missing from coverage report"><condition><not><contains string="${coverage.xml}" substring="name=&quot;sample/Logic&quot;"/></not></condition></fail></target>'
    guards = plugin('antrun', '<executions>' + execution('coverage-reset', 'initialize', ['run'], f'<configuration>{reset}</configuration>') +
                    execution('coverage-presence', 'verify', ['run'], f'<configuration>{guard}</configuration>') + '</executions>')
    # Mandatory core coverage/tests are inherited by code modules through management.
    managed = compiler + unit + integration + jacoco + guards + plugin("spotless") + "".join(plugin(k) for k in ("clean", "resources", "jar", "help"))
    parent = f'''<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
    <groupId>skill.fixture</groupId><artifactId>jvm-quality-fixture</artifactId><version>1</version><packaging>pom</packaging>
    <modules>{''.join('<module>'+m+'</module>' for m in MODULES)}<module>empty</module></modules>
    <properties>{properties}</properties><dependencyManagement><dependencies><dependency>
    <groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>${{junit.version}}</version><scope>test</scope>
    </dependency></dependencies></dependencyManagement><build><pluginManagement><plugins>{managed}</plugins></pluginManagement>
    <plugins>{enforcer}</plugins></build></project>'''
    write(root, 'pom.xml', parent)
    write(root, '.editorconfig', 'root = true\n\n[*]\ncharset = utf-8\nend_of_line = lf\ninsert_final_newline = true\n\n[*.{kt,kts}]\nindent_size = 4\nktlint_code_style = ktlint_official\n')
    write(root, 'checkstyle.xml', '''<?xml version="1.0"?>
    <!DOCTYPE module PUBLIC "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN" "https://checkstyle.org/dtds/configuration_1_3.dtd">
    <module name="Checker"><property name="severity" value="error"/><module name="TreeWalker">
    <module name="AvoidStarImport"/><module name="TypeName"/></module></module>''')
    write(root, 'pmd.xml', '''<?xml version="1.0"?><ruleset name="Focused fixture" xmlns="http://pmd.sourceforge.net/ruleset/2.0.0">
    <description>Only an independently observable correctness rule.</description>
    <rule ref="category/java/errorprone.xml/EmptyCatchBlock"/></ruleset>''')
    write(root, 'detekt.yml', '''build:
  maxIssues: 0
potential-bugs:
  active: true
  UnnecessaryNotNullOperator:
    active: true
exceptions:
  active: true
  SwallowedException:
    active: true
''')
    # Detekt on an isolated tool classpath; analyzed classpath supplied separately.
    exports = ''.join(f'<arg>-J--add-exports=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED</arg>' for p in ('api','file','main','model','parser','processing','tree','util'))
    exports += ''.join(f'<arg>-J--add-opens=jdk.compiler/com.sun.tools.javac.{p}=ALL-UNNAMED</arg>' for p in ('code','comp'))
    for module in MODULES:
        has_java, has_kotlin = module != 'kotlin-only', module != 'java-only'
        declarations = ''.join(plugin(k) for k in ('compiler','surefire','failsafe','jacoco'))
        if not has_kotlin:
            declarations = plugin('antrun') + declarations
            declarations = declarations.replace(plugin('jacoco'), plugin('jacoco', '<executions>' + execution('child-agent', 'pre-integration-test', ['prepare-agent'], '<configuration><propertyName>coverage.child.args</propertyName><destFile>${project.build.directory}/child.exec</destFile></configuration>') + '</executions>'))
        fmt = ''
        if has_java:
            fmt += '<java><includes><include>src/main/java/**/*.java</include><include>src/test/java/**/*.java</include></includes><googleJavaFormat><version>${formatter.version}</version></googleJavaFormat></java>'
        if has_kotlin:
            fmt += '<kotlin><includes><include>src/main/kotlin/**/*.kt</include><include>src/test/kotlin/**/*.kt</include></includes><ktlint><version>${ktlint.version}</version></ktlint></kotlin>'
        declarations += plugin('spotless', f'<configuration>{fmt}</configuration><executions>' + execution('format-check','verify',['check']) + '</executions>')
        if has_java:
            declarations += plugin('checkstyle_plugin', '''<configuration><configLocation>${fixture.root}/checkstyle.xml</configLocation>
            <includeTestSourceDirectory>true</includeTestSourceDirectory><includeResources>false</includeResources>
            <includeTestResources>false</includeTestResources><failOnViolation>true</failOnViolation></configuration>
            <dependencies><dependency><groupId>com.puppycrawl.tools</groupId><artifactId>checkstyle</artifactId><version>${checkstyle.version}</version></dependency></dependencies>
            <executions>''' + execution('style','verify',['check']) + '</executions>')
        kotlin = ''
        if has_kotlin:
            kotlin = plugin('kotlin', '''<configuration><jvmTarget>${maven.compiler.release}</jvmTarget>
            <args><arg>-Xjdk-release=${maven.compiler.release}</arg></args></configuration><executions>''' +
              execution('kotlin-compile','process-sources',['compile'],'''<configuration><sourceDirs>
              <sourceDir>${project.basedir}/src/main/kotlin</sourceDir><sourceDir>${project.basedir}/src/main/java</sourceDir></sourceDirs></configuration>''') +
              execution('kotlin-test','process-test-sources',['test-compile'],'''<configuration><sourceDirs>
              <sourceDir>${project.basedir}/src/test/kotlin</sourceDir><sourceDir>${project.basedir}/src/test/java</sourceDir></sourceDirs></configuration>''') + '</executions>')
            # Tool dependencies resolved in a separate Antrun execution/plugin realm.
            detekt = plugin('antrun', '''<dependencies><dependency><groupId>io.gitlab.arturbosch.detekt</groupId><artifactId>detekt-cli</artifactId>
            <version>${detekt.version}</version><classifier>all</classifier></dependency></dependencies><executions>''' +
              execution('detekt','verify',['run'],'''<configuration><target><java classname="io.gitlab.arturbosch.detekt.cli.Main" fork="true" failonerror="true">
              <classpath refid="maven.plugin.classpath"/><arg value="--input"/><arg value="${project.basedir}/src/main/kotlin,${project.basedir}/src/test/kotlin"/>
              <arg value="--config"/><arg value="${fixture.root}/detekt.yml"/>
              <arg value="--classpath"/><arg pathref="maven.test.classpath"/>
              <arg value="--jvm-target"/><arg value="${maven.compiler.release}"/>
              </java></target></configuration>''') + '</executions>')
            declarations += detekt
        # Full Java analyzer stack is opt-in for probing each checker independently.
        java_profile = ''
        if has_java:
            ep = plugin('compiler', f'''<configuration><fork>true</fork><compilerArgs>
            <arg>-Xlint:deprecation</arg><arg>-XDcompilePolicy=simple</arg><arg>--should-stop=ifError=FLOW</arg>
            <arg>-Xplugin:ErrorProne -XepDisableAllChecks -Xep:DeadException:ERROR</arg>{exports}</compilerArgs>
            <annotationProcessorPaths><path><groupId>com.google.errorprone</groupId><artifactId>error_prone_core</artifactId>
            <version>${{errorprone.version}}</version></path></annotationProcessorPaths></configuration>''')
            bugs = plugin('spotbugs', '''<configuration><effort>Max</effort><threshold>High</threshold><failOnError>true</failOnError>
            <plugins><plugin><groupId>com.h3xstream.findsecbugs</groupId><artifactId>findsecbugs-plugin</artifactId>
            <version>${findsecbugs.version}</version></plugin></plugins></configuration><executions>''' + execution('bugs','prepare-package',['check']) + '</executions>')
            pmd = plugin('pmd', '''<configuration><rulesets><ruleset>${fixture.root}/pmd.xml</ruleset></rulesets>
            <linkXRef>false</linkXRef><failOnViolation>true</failOnViolation><printFailingErrors>true</printFailingErrors><includeTests>true</includeTests></configuration>
            <executions>''' + execution('pmd','prepare-package',['check','cpd-check']) + '</executions>')
            java_profile = f'<profile><id>java-analysis</id><build><plugins>{ep}{bugs}{pmd}</plugins></build></profile>'
        dependency = '<dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><scope>test</scope></dependency>'
        if has_kotlin:
            dependency += '<dependency><groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-stdlib</artifactId><version>${kotlin.version}</version></dependency>'
        pom = f'''<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
        <parent><groupId>skill.fixture</groupId><artifactId>jvm-quality-fixture</artifactId><version>1</version></parent>
        <artifactId>{module}</artifactId><properties><coverage.required>true</coverage.required></properties>
        <dependencies>{dependency}</dependencies><build><plugins>{kotlin}</plugins></build>
        <profiles><profile><id>quality</id><build><plugins>{declarations}</plugins></build></profile>{java_profile}</profiles></project>'''
        write(root, module+'/pom.xml', pom)
        if not has_kotlin:
            logic = '''package sample;
public class Logic {
  public int signed(int value) { if (value < 0) { return -value; } return value; }
  public int integrated() { return 7; }
}
'''
            write(root, module+'/src/main/java/sample/Logic.java', logic)
        else:
            extra = '\n    fun fromJava(value: Int): Int = Bridge.twice(value)\n' if has_java else ''
            write(root, module+'/src/main/kotlin/sample/Logic.kt', '''package sample
class Logic {
    fun signed(value: Int): Int = if (value < 0) -value else value
    fun integrated(): Int = 7
''' + extra + '}\n')
        if has_java and has_kotlin:
            write(root, module+'/src/main/java/sample/Bridge.java', '''package sample;
public class Bridge {
  public static int twice(int value) { return value * 2; }
  public int fromKotlin() { return new Logic().integrated(); }
}
''')
        if has_java:
            extra = 'assertEquals(4, logic.fromJava(2)); assertEquals(7, new Bridge().fromKotlin());' if has_kotlin else ''
            write(root, module+'/src/test/java/sample/JavaTest.java', '''package sample;
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
class JavaTest {
  @Test void coversBranches() {
    assertEquals("preserved", System.getProperty("quality.sentinel"));
    assertEquals("active", System.getProperty("quality.agent"));
    Logic logic = new Logic(); assertEquals(2, logic.signed(-2)); assertEquals(2, logic.signed(2));
''' + extra + '\n  }\n}\n')
            write(root, module+'/src/test/java/sample/LogicIT.java', '''package sample;
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
class LogicIT {
  @Test void integration() {
    assertEquals("preserved", System.getProperty("quality.sentinel"));
    assertEquals("active", System.getProperty("quality.agent"));
    assertEquals(7, new Logic().integrated());
  }
}
''')
        if has_kotlin:
            write(root, module+'/src/test/kotlin/sample/KotlinTest.kt', '''package sample
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
class KotlinTest {
    @Test
    fun coversBranches() {
        assertEquals("preserved", System.getProperty("quality.sentinel"))
        assertEquals("active", System.getProperty("quality.agent"))
        assertEquals(2, Logic().signed(-2))
        assertEquals(2, Logic().signed(2))
    }
}
''')
            if not has_java:
                write(root, module+'/src/test/kotlin/sample/LogicIT.kt', '''package sample
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
class LogicIT {
    @Test
    fun integration() {
        assertEquals("preserved", System.getProperty("quality.sentinel"))
        assertEquals("active", System.getProperty("quality.agent"))
        assertEquals(7, Logic().integrated())
    }
}
''')
    write(root, 'java-only/src/main/java/sample/ChildMain.java', "package sample; public class ChildMain { private ChildMain() {} public static void main(String[] args) { System.out.println(new Logic().integrated()); } }\n")
    write(root, 'java-only/src/test/java/sample/ChildIT.java', '''package sample;
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
class ChildIT {
  @Test void childCoverage() throws Exception {
    java.util.List<String> command = new java.util.ArrayList<>();
    command.add(Path.of(System.getProperty("java.home"), "bin", "java").toString());
    String agent = System.getProperty("quality.child.agent", "");
    if (!agent.isBlank()) { command.add(agent); }
    command.add("-cp"); command.add(System.getProperty("java.class.path")); command.add("sample.ChildMain");
    Process child = new ProcessBuilder(command).start();
    String output = new String(child.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
    assertEquals(0, child.waitFor());
    assertEquals("7", output);
  }
}
''')
    write(root, 'empty/pom.xml', '''<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>
    <parent><groupId>skill.fixture</groupId><artifactId>jvm-quality-fixture</artifactId><version>1</version></parent>
    <artifactId>empty</artifactId><packaging>pom</packaging></project>''')


class Harness:
    def __init__(self, root):
        self.root = root
        self.results = json.loads((root/"results.json").read_text()) if (root/"results.json").exists() else []
        self.logs = root / 'logs'
        self.logs.mkdir(exist_ok=True)

    def run(self, name, args, expect=None, marker=None, wrapper=True):
        command = [str(self.root/'mvnw') if wrapper else 'mvn', '-B', '-ntp', *args]
        before_sources = self.source_hashes()
        started = time.monotonic()
        result = subprocess.run(command, cwd=self.root, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=900)
        log_path = self.logs / f'{len(self.results):03d}-{name}.log'
        log_path.write_text(result.stdout)
        passed = (result.returncode == 0) if expect is None else (result.returncode != 0 and marker.lower() in result.stdout.lower())
        unchanged = before_sources == self.source_hashes()
        if 'verify' in args and not unchanged:
            passed = False
        record = {'name': name, 'log': str(log_path.relative_to(self.root)), 'sources_unchanged': unchanged, 'command': command, 'exit_code': result.returncode,
                  'expected_diagnostic': marker, 'passed': passed,
                  'seconds': round(time.monotonic()-started, 2)}
        self.results.append(record)
        self.save()
        print(f'{name}: {"PASS" if passed else "FAIL"} (exit {result.returncode})', flush=True)
        if not passed:
            print(result.stdout[-6500:], flush=True)
            raise RuntimeError('Unexpected result: '+name)
        return result.stdout

    def source_hashes(self):
        return {str(p.relative_to(self.root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.glob('*/src/**/*.?*') if p.is_file() and p.suffix in ('.java', '.kt')}

    def save(self):
        (self.root/'results.json').write_text(json.dumps(self.results, indent=2)+'\n')

    def mutate(self, name, file, old, new, marker, args=None, format_first=True):
        path = self.root/file
        original = path.read_text()
        if old not in original:
            raise ValueError('Mutation did not match '+file)
        path.write_text(original.replace(old, new))
        try:
            if format_first:
                self.run(name+'-format', ['-Pquality', '-pl', file.split('/')[0], 'spotless:apply'])
            before = path.read_bytes()
            self.run(name, args or ['-Pquality,java-analysis','-pl',file.split('/')[0],'verify'], expect='failure', marker=marker)
            if path.read_bytes() != before:
                raise RuntimeError('Verification mutated source: '+name)
        finally:
            path.write_text(original)


def check_reports(harness):
    report = {}
    for module in MODULES:
        root = harness.root/module
        counts = {}
        for kind in ('surefire','failsafe'):
            reports = list((root/('target/'+kind+'-reports')).glob('TEST-*.xml'))
            counts[kind] = sum(int(ET.parse(p).getroot().get('tests','0')) for p in reports)
            if not counts[kind]:
                raise RuntimeError('No discovered '+kind+' tests in '+module)
        if module == 'mixed':
            suites = {ET.parse(p).getroot().get('name') for p in (root/'target/surefire-reports').glob('TEST-*.xml')}
            if not {'sample.JavaTest','sample.KotlinTest'} <= suites:
                raise RuntimeError('Mixed-language tests not both discovered')
        tree = ET.parse(root/'target/site/jacoco/jacoco.xml')
        classes = [c.get('name') for c in tree.findall('./package/class')]
        counters = {c.get('type'):{'missed':int(c.get('missed')),'covered':int(c.get('covered'))} for c in tree.findall('./counter')}
        if 'sample/Logic' not in classes or counters['LINE']['covered'] == 0 or counters['BRANCH']['covered'] == 0:
            raise RuntimeError('Empty/wrong production coverage in '+module)
        report[module] = {'test_counts': counts, 'classes': classes, 'counters': counters}
    (harness.root/'report-evidence.json').write_text(json.dumps(report,indent=2)+'\n')


def inspect_effective(harness):
    summary = {}
    for module in MODULES:
        output = harness.root / ('effective-'+module+'.xml')
        harness.run('effective-'+module, ['-Pquality,java-analysis', '-pl', module,
                    'help:effective-pom', '-Doutput='+str(output)])
        tree = ET.parse(output)
        plugins = tree.findall('./m:build/m:plugins/m:plugin', NS)
        executions = {p.findtext('m:artifactId', namespaces=NS):
            [g.text for g in p.findall('./m:executions/m:execution/m:goals/m:goal', NS)] for p in plugins}
        for name, goal in [('maven-surefire-plugin','test'),('maven-failsafe-plugin','verify'),('jacoco-maven-plugin','check'),('spotless-maven-plugin','check')]:
            if goal not in executions.get(name, []):
                raise RuntimeError('Missing inherited execution '+name+' in '+module)
        if module == 'kotlin-only' and any(name in executions for name in ('maven-checkstyle-plugin','spotbugs-maven-plugin','maven-pmd-plugin')):
            raise RuntimeError('Java analyzers leaked into Kotlin-only module')
        summary[module] = executions
    (harness.root/'effective-evidence.json').write_text(json.dumps(summary, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--versions', type=Path, required=True, help='Project-owned JSON pins outside the skills')
    parser.add_argument('--resolve-versions', action='store_true', help='Resolve stable candidates, write JSON, and exit')
    parser.add_argument('--output', type=Path, help='New, nonexistent disposable fixture directory')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--existing', type=Path, help='Resume this harness-owned fixture after investigating a failure')
    parser.add_argument('--case', choices=['baseline','mutations','java-analysis','runtime'], default='baseline')
    args = parser.parse_args()
    if args.resolve_versions:
        resolve_versions(args.versions)
        return
    versions = json.loads(args.versions.read_text())['versions']
    for key in ARTIFACTS:
        if not re.fullmatch(r'\d+(?:\.\d+)+', versions.get(key,'')):
            parser.error('Missing/nonstable project pin: '+key)
    if args.existing:
        root = args.existing.resolve()
        if not (root/'.jvm-quality-fixture').is_file():
            parser.error('--existing must be a harness-owned fixture')
    else:
        root = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='jvm-quality-'))/'fixture'
        root.mkdir(parents=True, exist_ok=False)
        write(root, '.jvm-quality-fixture', 'Disposable JVM skill validation fixture\n')
        shutil.copyfile(args.versions, root/'versions.json')
        create_fixture(root, versions)
    harness = Harness(root)
    print('Fixture: '+str(root), flush=True)
    if args.prepare_only:
        return
    if not (root/'mvnw').exists():
        harness.run('wrapper', [f'org.apache.maven.plugins:maven-wrapper-plugin:{versions["wrapper"]}:wrapper',f'-Dmaven={versions["maven"]}'],wrapper=False)
    if args.case == 'baseline':
        harness.run('format',['-Pquality','spotless:apply'])
        harness.run('clean-reactor',['-Pquality,java-analysis','clean','verify'])
        check_reports(harness)
        inspect_effective(harness)
        harness.run('incremental-reactor',['-Pquality,java-analysis','verify'])
    elif args.case == 'mutations':
        harness.mutate('java-format', 'java-only/src/main/java/sample/Logic.java','public class Logic {','public   class Logic {','spotless',format_first=False)
        harness.mutate('kotlin-format','kotlin-only/src/main/kotlin/sample/Logic.kt','class Logic {','class   Logic {','spotless',format_first=False)
        harness.mutate('integration-failure','java-only/src/test/java/sample/LogicIT.java','assertEquals(7,','assertEquals(8,','There are test failures')
        harness.mutate('module-branch-floor','java-only/src/test/java/sample/JavaTest.java','assertEquals(2, logic.signed(-2));','', 'coverage checks have not been met')
        harness.run('missing-agent',['-Pquality','-Djacoco.skip=true','verify'],expect='failure',marker='Required coverage data missing or empty')
        harness.run('missing-integration-coverage',['-Pquality','-DskipITs=true','verify'],expect='failure',marker='Required coverage data missing or empty')
        harness.run('missing-required-tests',['-Pquality','-DskipTests','verify'],expect='failure',marker='Required coverage data missing or empty')
        harness.mutate('compiler-warning','java-only/src/main/java/sample/Logic.java','return 7;','return new java.util.Date().getYear();','warnings found and -Werror specified')
        harness.mutate('java-api','java-only/src/main/java/sample/Logic.java','return 7;','return java.util.List.of(7).getFirst();','cannot find symbol')
        harness.mutate('kotlin-api','kotlin-only/src/main/kotlin/sample/Logic.kt','fun integrated(): Int = 7','fun integrated(): Int = java.util.List.of(7).getFirst()','getFirst')
        harness.mutate('detekt-finding','kotlin-only/src/main/kotlin/sample/Logic.kt','fun integrated(): Int = 7','fun integrated(): Int { val value: String = "known"; return value!!.length + 2 }','UnnecessaryNotNullOperator')
        harness.mutate('java-style-test','java-only/src/test/java/sample/JavaTest.java','import org.junit.jupiter.api.Test;','import org.junit.jupiter.api.*;','AvoidStarImport')
        harness.run('restored-reactor',['-Pquality,java-analysis','verify'])
        check_reports(harness)
    elif args.case == 'java-analysis':
        harness.run('analysis-format',['-Pquality','-pl','java-only','spotless:apply'])
        harness.run('analysis-clean',['-Pquality,java-analysis','-pl','java-only','clean','verify'])
        harness.mutate('errorprone-finding','java-only/src/main/java/sample/Logic.java','return 7;','new IllegalStateException("unused"); return 7;','DeadException',args=['-Pquality,java-analysis','-pl','java-only','verify'])
        logic = root/'java-only/src/main/java/sample/Logic.java'
        test = root/'java-only/src/test/java/sample/JavaTest.java'
        old_logic, old_test = logic.read_text(), test.read_text()
        try:
            logic.write_text(old_logic.replace('public class Logic {', 'public class Logic { public int bug() { Object value = null; return value.hashCode(); }'))
            test.write_text(old_test.replace('Logic logic = new Logic();', 'org.junit.jupiter.api.Assertions.assertThrows(NullPointerException.class, () -> new Logic().bug()); Logic logic = new Logic();'))
            harness.run('spotbugs-finding-format', ['-Pquality','-pl','java-only','spotless:apply'])
            harness.run('spotbugs-finding', ['-Pquality,java-analysis','-pl','java-only','verify'], expect='failure', marker='NP_ALWAYS_NULL')
        finally:
            logic.write_text(old_logic)
            test.write_text(old_test)
        harness.mutate('pmd-finding','java-only/src/main/java/sample/Logic.java','return 7;','try { Integer.parseInt("7"); } catch (NumberFormatException problem) { } return 7;','EmptyCatchBlock',args=['-Pquality,java-analysis','-pl','java-only','verify'])
        repeated = 'int total = 0; ' + ' '.join(f'total += {i};' for i in range(1,41)) + ' assertEquals(820, total);'
        methods = 'class JavaTest { void duplicateOne() { ' + repeated + ' } void duplicateTwo() { ' + repeated + ' }'
        harness.mutate('cpd-finding','java-only/src/test/java/sample/JavaTest.java','class JavaTest {',methods,'duplicated',args=['-Pquality,java-analysis','-pl','java-only','verify'])
        harness.run('analysis-restored' ,['-Pquality,java-analysis','-pl','java-only','verify'])
    elif args.case == 'runtime':
        # Caller supplies JAVA_HOME/PATH for supported-runtime JDK; analyzer job is separate.
        harness.run('runtime-tests',['-Denforcer.skip=true','-Pquality','test'])


if __name__ == '__main__':
    main()
