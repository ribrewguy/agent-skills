#!/usr/bin/env python3
"""Compile and probe fresh Java design-eval outputs. No project changes or dependencies.

Use --outputs for a directory containing case-4 through case-8 Java sources.
Case-9 is independently graded prose. The release is a fixture input, not a skill pin.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

SUPPORT = r'''
import java.util.*;
import java.math.BigDecimal;
final class Probe {
  interface Work { void run() throws Exception; }
  static int failures;
  static void run(String id, Work work) {
    try { work.run(); System.out.println("PASS\t"+id); }
    catch (Throwable failure) { failures++; System.out.println("FAIL\t"+id+"\t"+failure); }
  }
  static void yes(boolean value) { if (!value) throw new AssertionError("condition false"); }
  static void reject(Work work) throws Exception {
    try { work.run(); } catch (IllegalArgumentException | NullPointerException expected) { return; }
    throw new AssertionError("invalid input accepted");
  }
  static void finish() { if (failures > 0) throw new AssertionError(failures+" failed probes"); }
}
'''

CASES = {
4: r'''
public class ContractProbe {
  static ShipmentSnapshot sample() { return new ShipmentSnapshot("s", new ArrayList<>(List.of(new Parcel("A", 2))), new byte[]{1,2}); }
  public static void main(String[] args) {
    Probe.run("input-aliases", () -> {
      Parcel p = new Parcel("A",2); List<Parcel> input = new ArrayList<>(List.of(p,p)); byte[] label = {1,2};
      ShipmentSnapshot s = new ShipmentSnapshot("s",input,label);
      p.setSku("changed"); p.setQuantity(-1); input.clear(); label[0]=9;
      Probe.yes(s.id().equals("s") && s.parcels().size()==2 && s.parcels().get(0).sku().equals("A") && s.parcels().get(1).quantity()==2 && s.label()[0]==1);
    });
    Probe.run("nested-output-alias", () -> {
      ShipmentSnapshot s=sample(); s.parcels().get(0).setQuantity(99); s.parcels().get(0).setSku("changed");
      Probe.yes(s.parcels().get(0).quantity()==2 && s.parcels().get(0).sku().equals("A"));
    });
    Probe.run("array-output-alias", () -> { ShipmentSnapshot s=sample(); s.label()[0]=9; Probe.yes(s.label()[0]==1); });
    Probe.run("collection-output-alias", () -> {
      ShipmentSnapshot s=sample(); try {s.parcels().clear();} catch(UnsupportedOperationException allowed){}
      Probe.yes(s.parcels().size()==1);
    });
    Probe.run("null-and-blank-boundaries", () -> {
      Probe.reject(() -> new ShipmentSnapshot(null,List.of(),new byte[0]));
      Probe.reject(() -> new ShipmentSnapshot(" ",List.of(),new byte[0]));
      Probe.reject(() -> new ShipmentSnapshot("s",null,new byte[0]));
      Probe.reject(() -> new ShipmentSnapshot("s",List.of(),null));
      Probe.reject(() -> new ShipmentSnapshot("s",Arrays.asList((Parcel)null),new byte[0]));
    });
    Probe.run("invalid-elements", () -> {
      Probe.reject(() -> new ShipmentSnapshot("s",List.of(new Parcel(null,1)),new byte[0]));
      Probe.reject(() -> new ShipmentSnapshot("s",List.of(new Parcel(" ",1)),new byte[0]));
      Probe.reject(() -> new ShipmentSnapshot("s",List.of(new Parcel("A",0)),new byte[0]));
      Probe.reject(() -> new ShipmentSnapshot("s",List.of(new Parcel("A",-1)),new byte[0]));
    });
    Probe.run("empty-controls", () -> {ShipmentSnapshot s=new ShipmentSnapshot("s",List.of(),new byte[0]); Probe.yes(s.parcels().isEmpty() && s.label().length==0);});
    Probe.run("validate-retained-element", () -> {
      Parcel p=new Parcel("A",2) {int reads; public int quantity() {return ++reads==1?2:-1;}};
      try {ShipmentSnapshot s=new ShipmentSnapshot("s",List.of(p),new byte[0]); Probe.yes(s.parcels().get(0).quantity()>0);}
      catch(IllegalArgumentException | NullPointerException allowed){}
    });
    Probe.finish();
  }
}
''',
5: r'''
public class ContractProbe {
  static class HostileDate extends Date {HostileDate(long time){super(time);} public Object clone(){return this;}}
  public static void main(String[] args) {
    Probe.run("input-dates-owned", () -> {Date start=new Date(10), end=new Date(50); DateRange r=new DateRange(start,end); start.setTime(100);end.setTime(-1);Probe.yes(r.start().getTime()==10 && r.end().getTime()==50 && r.durationMillis()==40);});
    Probe.run("output-dates-owned", () -> {DateRange r=new DateRange(new Date(10),new Date(50));r.start().setTime(100);r.end().setTime(-1);Probe.yes(r.start().getTime()==10 && r.end().getTime()==50);});
    Probe.run("subtype-clone-not-trusted", () -> {Date s=new HostileDate(10),e=new HostileDate(50);DateRange r=new DateRange(s,e);s.setTime(100);e.setTime(-1);Probe.yes(r.start().getTime()==10 && r.end().getTime()==50);});
    Probe.run("range-validation", () -> {Probe.reject(() -> new DateRange(null,new Date()));Probe.reject(() -> new DateRange(new Date(),null));Probe.reject(() -> new DateRange(new Date(50),new Date(10)));});
    Probe.run("equal-endpoint-control", () -> {DateRange r=new DateRange(new Date(10),new Date(10));Probe.yes(r.durationMillis()==0);});
    Probe.run("validate-retained-date", () -> {
      Date s=new Date(0){int reads; public long getTime(){return ++reads==1?0:300;}};
      try {DateRange r=new DateRange(s,new Date(200));Probe.yes(r.start().getTime()<=r.end().getTime());}catch(IllegalArgumentException allowed){}
    });
    Probe.finish();
  }
}
''',
6: r'''
public class ContractProbe {
  static StockLedger ledger(){return new StockLedger(new LinkedHashMap<>(Map.of("A",10,"B",5)));}
  public static void main(String[] args) {
    Probe.run("constructor-owns-map", () -> {Map<String,Integer> initial=new HashMap<>(Map.of("A",10));StockLedger l=new StockLedger(initial);initial.put("A",0);Probe.yes(l.stock().get("A")==10);});
    Probe.run("valid-mutation-control", () -> {StockLedger l=ledger();l.reserve(Map.of("A",2,"B",1));Probe.yes(l.stock().equals(Map.of("A",8,"B",4)));l.reserve(Map.of("A",3));Probe.yes(l.stock().get("A")==5);});
    Probe.run("unknown-key-atomicity", () -> {StockLedger l=ledger();Map<String,Integer> req=new LinkedHashMap<>();req.put("A",1);req.put("missing",1);Probe.reject(() -> l.reserve(req));Probe.yes(l.stock().equals(Map.of("A",10,"B",5)));});
    Probe.run("late-invalid-atomicity", () -> {StockLedger l=ledger();Map<String,Integer> req=new LinkedHashMap<>();req.put("A",1);req.put("B",6);Probe.reject(() -> l.reserve(req));Probe.yes(l.stock().equals(Map.of("A",10,"B",5)));});
    Probe.run("snapshot-not-live-view", () -> {StockLedger l=ledger();Map<String,Integer> before=l.stock();l.reserve(Map.of("A",1));Probe.yes(before.get("A")==10 && l.stock().get("A")==9);});
    Probe.run("snapshot-read-only", () -> {StockLedger l=ledger();boolean rejected=false;try{l.stock().put("A",0);}catch(UnsupportedOperationException expected){rejected=true;}Probe.yes(rejected && l.stock().get("A")==10);});
    Probe.run("null-request-entries", () -> {StockLedger l=ledger();Map<String,Integer> req=new HashMap<>();req.put("A",null);Probe.reject(() -> l.reserve(req));req.clear();req.put(null,1);Probe.reject(() -> l.reserve(req));Probe.reject(() -> l.reserve(null));Probe.yes(l.stock().equals(Map.of("A",10,"B",5)));});
    Probe.run("nonpositive-request", () -> {StockLedger l=ledger();Probe.reject(() -> l.reserve(Map.of("A",0)));Probe.reject(() -> l.reserve(Map.of("A",-1)));Probe.yes(l.stock().get("A")==10);});
    Probe.run("initial-invariants", () -> {Probe.reject(() -> new StockLedger(null));Probe.reject(() -> new StockLedger(Map.of(" ",1)));Probe.reject(() -> new StockLedger(Map.of("A",-1)));Map<String,Integer> bad=new HashMap<>();bad.put("A",null);Probe.reject(() -> new StockLedger(bad));});
    Probe.run("empty-and-zero-controls", () -> {StockLedger l=ledger();l.reserve(Map.of());Probe.yes(l.stock().get("A")==10);Probe.yes(new StockLedger(Map.of()).stock().isEmpty());Probe.yes(new StockLedger(Map.of("A",0)).stock().get("A")==0);});
    Probe.finish();
  }
}
''',
7: r'''
public class ContractProbe {
  public static void main(String[] args) {
    Probe.run("bulk-and-duplicates", () -> {CountingSet<String>s=new CountingSet<>();Probe.yes(s.addAll(Arrays.asList("a","a","b")));Probe.yes(s.totalAdded()==2 && s.size()==2);Probe.yes(!s.add("b") && !s.addAll(List.of("a","b")) && s.totalAdded()==2);});
    Probe.run("remove-and-reinsert", () -> {CountingSet<String>s=new CountingSet<>();s.add("a");s.remove("a");s.add("a");Probe.yes(s.totalAdded()==2 && s.size()==1);});
    Probe.run("iterator-removal", () -> {CountingSet<String>s=new CountingSet<>();s.add("a");Iterator<String>i=s.iterator();i.next();i.remove();Probe.yes(s.isEmpty() && s.totalAdded()==1);});
    Probe.run("clear-preserves-total", () -> {CountingSet<String>s=new CountingSet<>();s.addAll(List.of("a","b"));s.clear();s.add("c");Probe.yes(s.totalAdded()==3 && s.equals(Set.of("c")));});
    Probe.run("set-equality-hash", () -> {CountingSet<String>s=new CountingSet<>();s.addAll(List.of("a","b"));Set<String>other=new HashSet<>(List.of("b","a"));Probe.yes(s.equals(other) && other.equals(s) && s.hashCode()==other.hashCode());});
    Probe.run("set-removeAll-retainAll", () -> {CountingSet<String>s=new CountingSet<>();s.addAll(List.of("a","b","c"));s.removeAll(List.of("a"));s.retainAll(List.of("b"));Probe.yes(s.equals(Set.of("b")) && s.totalAdded()==3);});
    Probe.finish();
  }
}
''',
8: r'''
public class ContractProbe {
  static Money money(String amount,String currency){return new Money(new BigDecimal(amount),currency);}
  public static void main(String[] args) {
    Probe.run("scale-equality", () -> {Money a=money("1.0","USD"),b=money("1.00","USD");Probe.yes(a.equals(b) && b.equals(a) && a.hashCode()==b.hashCode() && a.compareTo(b)==0);});
    Probe.run("hash-collection-lookup", () -> {Map<Money,String>m=new HashMap<>();m.put(money("1.00","USD"),"found");Probe.yes("found".equals(m.get(money("1.0","USD"))));Set<Money>s=new HashSet<>(List.of(money("1.0","USD"),money("1.00","USD")));Probe.yes(s.size()==1);});
    Probe.run("currency-identity-and-order", () -> {Money a=money("1","EUR"),b=money("1","USD");Probe.yes(!a.equals(b) && a.compareTo(b)<0 && b.compareTo(a)>0);});
    Probe.run("numeric-order", () -> {Probe.yes(money("2","USD").compareTo(money("10","USD"))<0);});
    Probe.run("exact-decimal-addition", () -> {Probe.yes(money("0.1","USD").plus(money("0.2","USD")).equals(money("0.3","USD")));Probe.yes(money("100000000000000000000.1","USD").plus(money("0.2","USD")).equals(money("100000000000000000000.3","USD")));});
    Probe.run("cross-currency-rejection", () -> {Probe.reject(() -> money("1","USD").plus(money("1","EUR")));});
    Probe.run("constructor-invariants", () -> {Probe.reject(() -> new Money(null,"USD"));Probe.reject(() -> money("1",null));Probe.reject(() -> money("1","usd"));Probe.reject(() -> money("1","US"));Probe.reject(() -> money("1"," "));});
    Probe.run("negative-and-zero-controls", () -> {Probe.yes(money("-1","USD").plus(money("1","USD")).equals(money("0.00","USD")));});
    Probe.finish();
  }
}
''',
}


def evaluate(outputs, java, javac, release):
    results=[]
    for number, test in CASES.items():
        source=outputs/('case-'+str(number))
        files=sorted(source.glob('*.java'))
        with tempfile.TemporaryDirectory(prefix='java-design-probe-') as directory:
            run=Path(directory)
            (run/'Probe.java').write_text(SUPPORT)
            (run/'ContractProbe.java').write_text('import java.util.*;\nimport java.math.BigDecimal;\n'+test)
            command=[javac,'--release',str(release),'-d',str(run),*map(str,files),str(run/'Probe.java'),str(run/'ContractProbe.java')]
            compilation=subprocess.run(command,text=True,capture_output=True,timeout=90)
            record={'case':number,'compile_exit':compilation.returncode,'compile_output':compilation.stdout+compilation.stderr}
            if compilation.returncode==0:
                execution=subprocess.run([java,'-cp',str(run),'ContractProbe'],text=True,capture_output=True,timeout=30)
                record.update({'run_exit':execution.returncode,'output':execution.stdout,'stderr':execution.stderr,'probes':[]})
                for line in execution.stdout.splitlines():
                    if line.startswith(('PASS\t','FAIL\t')):
                        status,name,*detail=line.split('\t');record['probes'].append({'name':name,'passed':status=='PASS','detail':' '.join(detail)})
            results.append(record)
            print('case-'+str(number)+': compile='+str(record['compile_exit'])+' run='+str(record.get('run_exit','not run')),flush=True)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outputs',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--java',default='java')
    parser.add_argument('--javac',default='javac')
    parser.add_argument('--release',default=17,type=int)
    args=parser.parse_args()
    results=evaluate(args.outputs,args.java,args.javac,args.release)
    args.result.write_text(json.dumps({'release':args.release,'cases':results},indent=2)+'\n')
    if any(r['compile_exit'] or r.get('run_exit',1) for r in results):raise SystemExit(1)


if __name__=='__main__':main()
