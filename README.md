# POPCNT ORACLE
---

## 0. Recon

Tenemos un servicio que genera una clave RSA y un mensaje secreto `m`.

El servidor nos entrega:

```text
e
n
c
```

donde:

$$
c=m^e\bmod n
$$

Hasta aquí, nada demasiado extraño.

El problema aparece cuando el servidor empieza a aceptar valores `x`.

Si `x == m`, obtenemos la flag.

Si no:

```python
print(pow(x, d, n).bit_count())
```

No nos devuelve el plaintext.

Nos devuelve solamente su **Hamming Weight**, es decir, el número de bits `1`.

Parece poca información.

No lo es.

---

# 1. El objetivo

Tenemos:

$$
c=m^e\bmod n
$$

y queremos recuperar:

$$
m
$$

sin conocer:

$$
p,\;q,\;d
$$

Factorizar `n` sería la solución tradicional.

Pero no necesitamos hacerlo.

La oracle nos da otra superficie de ataque:

$$
HW(x^d\bmod n)
$$

La pregunta es:

> ¿Podemos construir un `x` cuyo plaintext conocido sea una transformación controlada de `m`?

La respuesta es sí.

---

# 2. RSA es multiplicativo

Sabemos que:

$$
c=m^e\bmod n
$$

Construyamos:

$$
x_k=c\cdot2^{ek}\bmod n
$$

Sustituyendo `c`:

$$
x_k=m^e2^{ek}\bmod n
$$

Ahora aplicamos la clave privada:

$$
x_k^d = (m^e2^{ek})^d
$$

Como:

$$
ed\equiv1\pmod{\varphi(n)}
$$

obtenemos:

$$
x_k^d\bmod n =
m2^k\bmod n
$$

Definimos:

$$
\boxed{v_k=m2^k\bmod n}
$$

Por lo tanto, cuando consultamos `x_k`, la oracle nos devuelve:

$$
\boxed{w_k=HW(v_k)}
$$

Esto convierte la oracle RSA en una oracle sobre:

$$
m,\;2m,\;4m,\;8m,\ldots
$$

todo módulo `n`.

---

# 3. El problema

Podríamos pensar:

> Si multiplicar por 2 simplemente desplaza los bits, entonces podemos ver cuándo cambia el `popcount` y recuperar los bits.

Pero hay un problema.

Tenemos:

$$
v_{k+1}=2v_k\bmod n
$$

Dependiendo del valor de `v_k`, pueden ocurrir dos cosas.

### Sin wrap

Si:

$$
2v_k<n
$$

entonces:

$$
v_{k+1}=2v_k
$$

Multiplicar por 2 es un desplazamiento binario:

```text
101101
   ↓ ×2
1011010
```

Por lo tanto:

$$
HW(v_{k+1})=HW(v_k)
$$

La Hamming Weight permanece constante.

---

### Con wrap

Si:

$$
2v_k\ge n
$$

entonces debemos restar `n`:

$$
v_{k+1}=2v_k-n
$$

Podemos escribir ambos casos como:

$$
\boxed{v_{k+1}=2v_k-b_kn}
$$

donde:

$$
b_k\in\{0,1\}
$$

Este `b_k` es el **carry/wrap bit** que queremos recuperar.

---

# 4. Una sola oracle no es suficiente

Con la primera secuencia tenemos:

$$
w_k=HW(v_k)
$$

Si `b = 0`:

$$
v_{k+1}=2v_k
$$

por lo que:

$$
w_{k+1}=w_k
$$

Pero si `b = 1`, el `popcount` puede cambiar...

...o puede coincidir accidentalmente.

Entonces:

```text
w[k] == w[k+1]
```

no significa necesariamente:

```text
b = 0
```

Tenemos información.

Pero no suficiente.

Necesitamos otra perspectiva.

---

# 5. Mirror

Aquí está la parte interesante.

Además de:

$$
x_k
$$

podemos consultar:

$$
\boxed{x'_k=n-x_k}
$$

Como:

$$
x'_k\equiv-x_k\pmod n
$$

al descifrar:

$$
x'_k{}^d\equiv(-x_k)^d\pmod n
$$

El exponente privado `d` es impar, así que:

$$
(-x_k)^d=-x_k^d
$$

Por lo tanto:

$$
x'_k{}^d\bmod n=n-v_k
$$

La segunda oracle nos da:

$$
\boxed{w'_k=HW(n-v_k)}
$$

Ahora tenemos dos visiones del mismo estado:

```text
w_k  = popcount(v_k)

w'_k = popcount(n - v_k)
```

Dos señales.

Un solo objetivo.

---

# 6. El truco

Recordemos:

$$
v_{k+1}=2v_k-b_kn
$$

Analicemos los dos posibles valores de `b`.

---

## 6.1. Cuando `b = 0`

Tenemos:

$$
v_{k+1}=2v_k
$$

Por lo tanto:

$$
HW(v_{k+1})=HW(v_k)
$$

Así que:

```text
w  -> flat
```

Ahora observamos el complemento:

$$
n-v_{k+1} =
n-2v_k
$$

No existe la misma conservación de Hamming Weight.

Normalmente:

```text
w' -> jump
```

Tenemos:

```text
w  = igual
w' = cambia
```

Por lo tanto:

$$
\boxed{b=0}
$$

---

# 7. Cuando `b = 1`

Ahora:

$$
v_{k+1}=2v_k-n
$$

Tomamos el complemento:

$$
n-v_{k+1}
$$

Sustituyendo:

$$
n-(2v_k-n)
$$

$$
=2n-2v_k
$$

$$
=2(n-v_k)
$$

Entonces:

$$
n-v_{k+1}=2(n-v_k)
$$

Multiplicar por 2 vuelve a ser solamente un desplazamiento binario.

Por lo tanto:

$$
HW(n-v_{k+1})=HW(n-v_k)
$$

Tenemos:

```text
w  = cambia
w' = igual
```

Por lo tanto:

$$
\boxed{b=1}
$$

---

# 8. La tabla que rompe la oracle

| `w`    | `w'`   | Resultado     |
| ------ | ------ | ------------- |
| cambia | igual  | `b = 1`       |
| igual  | cambia | `b = 0`       |
| igual  | igual  | ambiguo       |
| cambia | cambia | contradicción |

Esta es la pieza central del exploit.

No necesitamos que el `popcount` nos diga directamente el bit.

Hacemos algo mejor:

> Observamos cuál de las dos secuencias permanece necesariamente plana.

---

# 9. ¿Qué estamos recuperando realmente?

Los bits `b_k` corresponden a la expansión binaria de:

$$
\alpha=\frac mn
$$

Como:

$$
0\le m<n
$$

tenemos:

$$
0\le\frac mn<1
$$

Podemos escribir:

$$
\frac mn=0.b_1b_2b_3b_4\ldots_2
$$

Los `b_k` recuperados por la oracle son precisamente esos bits.

Por ejemplo:

```text
m/n = 0.101101001...
          ↑
       bits recuperados
```

Así que la oracle nos permite reconstruir progresivamente:

$$
\frac mn
$$

sin conocer `m`.

---

# 10. Las ambigüedades

Existe un caso incómodo:

```text
w  -> igual
w' -> igual
```

No sabemos si:

```text
b = 0
```

o:

```text
b = 1
```

Pero ahora el problema es mucho menor.

Con una sola oracle teníamos aproximadamente:

```text
~1044 bits ambiguos
```

Eso implicaría:

$$
2^{1044}
$$

posibilidades.

No.

Ni siquiera vamos a intentarlo.

Con las dos cadenas, solamente una pequeña cantidad de bits queda ambigua.

Por ejemplo:

```text
decoded: 21 ambiguous positions
```

Ahora el espacio es:

$$
2^{21}
$$

Eso sí es posible.

---

# 11. Construcción de `A`

El script recupera los primeros `K` bits:

```python
A = 0

for i in range(1, K + 1):
    A = (A << 1) | (bits[i] or 0)
```

Si tenemos:

```text
b1 b2 b3 b4
1  0  1  1
```

entonces:

$$
A=1011_2
$$

Es decir:

$$
A\approx2^K\frac mn
$$

Por lo tanto:

$$
An\approx2^Km
$$

y:

$$
\boxed{m\approx\frac{An}{2^K}}
$$

Como dividir entre \(2^K\) equivale a un shift:

```python
X = (A * n) >> K
```

obtenemos una aproximación extremadamente cercana a `m`.

---

# 12. ¿Por qué `X` y `X+1`?

Por el truncamiento producido al hacer:

$$
\left\lfloor\frac{An}{2^K}\right\rfloor
$$

el valor real de `m` queda en torno a:

$$
X
$$

o:

$$
X+1
$$

Por eso el código no busca alrededor de `X`.

Simplemente prueba:

```python
for m_c in (X, X + 1):
```

Esto reduce brutalmente el espacio de búsqueda.

---

# 13. Resolver los bits ambiguos

Supongamos que tenemos:

```text
101?10??011...
```

Cada `?` tiene dos posibilidades.

El programa construye inicialmente:

```text
A = bits conocidos
```

asumiendo:

```text
ambiguous = 0
```

Después:

```python
Pbase = A * n
```

Cada bit ambiguo `p` cambia `A` en:

$$
2^{K-p}
$$

Por lo tanto cambia `A*n` en:

$$
\boxed{2^{K-p}n}
$$

El código precalcula esas contribuciones:

```python
ds = [(1 << (K - p)) * n for p in P]
```

Así podemos activar o desactivar rápidamente cada bit ambiguo.

---

# 14. Gray Code

Podríamos recorrer:

```text
000
001
010
011
100
101
110
111
```

pero eso puede obligarnos a modificar varios bits entre estados.

El script utiliza una enumeración tipo **Gray Code**:

```text
000
001
011
010
110
111
101
100
```

La propiedad importante es:

> Entre dos estados consecutivos solamente cambia un bit.

Por ejemplo:

```text
001
011
```

solamente cambia el segundo bit.

Entonces podemos actualizar:

```python
curp += ds[t]
```

o:

```python
curp -= ds[t]
```

sin reconstruir todo `A*n`.

Esto es una optimización de velocidad.

---

# 15. Primer filtro: Hamming Weight de `m`

La primera consulta fue:

$$
x_0=c
$$

Como:

$$
c^d\bmod n=m
$$

la primera respuesta es:

$$
w_0=HW(m)
$$

Por eso:

```python
w0 = w[0]
```

y para cada candidato:

```python
if m_c.bit_count() != w0:
    continue
```

Si no tiene exactamente el mismo número de bits `1`, lo descartamos inmediatamente.

Barato.

Rápido.

Efectivo.

---

# 16. Filtros adicionales

El programa no se conforma con una sola comparación.

Utiliza algunas posiciones adicionales:

```python
fk = [97, 311, 509, 1013]
```

Para cada candidato calcula:

$$
HW(m_c2^k\bmod n)
$$

y lo compara con la respuesta real:

$$
w_k
$$

Por ejemplo:

$$
HW(m_c2^{97}\bmod n)=w_{97}
$$

Si falla:

```python
return False
```

El candidato muere.

No necesitamos gastar tiempo en la comprobación RSA.

---

# 17. La prueba definitiva

Finalmente:

```python
if pow(m_c, e, n) == c:
```

Estamos comprobando:

$$
\boxed{m_c^e\bmod n=c}
$$

Esta es la prueba definitiva.

Los filtros de `popcount` solamente reducen el número de candidatos.

La ecuación RSA confirma que encontramos el `m` original.

---

# 18. Enviar `m`

Cuando:

```python
found = m_c
```

tenemos:

$$
m_{recovered}=m
$$

Entonces enviamos:

```python
s.sendall(str(found).encode() + b"\n")
```

El servidor compara:

```python
if x == m:
```

Ahora:

```text
x == m
```

y obtenemos:

```text
FLAG
```

Game over.

---

# 19. Flujo del exploit

```text
                         RSA
                          │
                    c = m^e mod n
                          │
                          ▼
                ┌──────────────────┐
                │ Construir x_k    │
                │ c·2^(e·k) mod n  │
                └────────┬─────────┘
                         │
                         ▼
                 decrypt(x_k)
                         │
                         ▼
                  m·2^k mod n
                         │
                         ▼
                    w_k = HW()
                         │
                         │
                         │
                         ▼
                ┌──────────────────┐
                │ Construir x'_k   │
                │ n - x_k          │
                └────────┬─────────┘
                         │
                         ▼
                 decrypt(x'_k)
                         │
                         ▼
                    n - v_k
                         │
                         ▼
                   w'_k = HW()
                         │
                 ┌───────┴───────┐
                 │               │
                 ▼               ▼
                w_k             w'_k
                 │               │
                 └───────┬───────┘
                         ▼
                  comparar saltos
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
             b=0        b=1      ambiguo
              │          │          │
              └──────────┴──────────┘
                         │
                         ▼
                 bits de m/n
                         │
                         ▼
                  reconstruir A
                         │
                         ▼
                   estimar m
                         │
                         ▼
                 X / X+1 candidatos
                         │
                         ▼
                  popcount filter
                         │
                         ▼
                  filtros extra
                         │
                         ▼
                  RSA verification
                         │
                         ▼
                         m
                         │
                         ▼
                       FLAG
```

---

# 20. El código: visión por bloques

El solver puede dividirse conceptualmente en seis partes.

### 1. Conexión

```python
socket.create_connection(...)
```

Obtiene:

```text
e
n
c
```

---

### 2. Recolección

Construye:

$$
x_k=c2^{ek}\bmod n
$$

y:

$$
x'_k=n-x_k
$$

Obtiene:

```text
w
w'
```

---

### 3. Decodificación

Compara:

```python
w[i-1] != w[i]
wp[i-1] != wp[i]
```

y recupera:

```text
b = 0
b = 1
ambiguous
```

---

### 4. Reconstrucción

Convierte los bits recuperados en:

$$
A\approx2^K\frac mn
$$

y obtiene:

$$
X=\frac{An}{2^K}
$$

---

### 5. Búsqueda

Enumera únicamente las posiciones ambiguas.

Utiliza:

* Gray Code
* `popcount`
* filtros adicionales

---

### 6. Verificación

Comprueba:

$$
m^e\bmod n=c
$$

y envía `m`.

---

# 21. ¿Por qué no necesitamos factorizar RSA?

Este es probablemente el punto más interesante del challenge.

No estamos rompiendo RSA matemáticamente.

RSA sigue funcionando correctamente.

El problema está en la **oracle**.

El servidor nos permite calcular:

$$
HW(x^d\bmod n)
$$

para valores `x` elegidos por nosotros.

Gracias a la propiedad multiplicativa de RSA podemos transformar esa oracle en:

$$
HW(m2^k\bmod n)
$$

y:

$$
HW(n-m2^k\bmod n)
$$

Estas dos secuencias filtran información sobre la expansión binaria de:

$$
\frac mn
$$

Finalmente reconstruimos `m` sin conocer:

```text
p
q
d
```

---

# 22. Vulnerabilidad resumida

La vulnerabilidad puede expresarse así:

$$
\boxed{
\text{RSA multiplicativo}
+
\text{chosen ciphertext}
+
\text{leak de popcount}
}
$$

permite recuperar información suficiente sobre `m`.

El servidor debería evitar revelar información derivada del plaintext RSA.

Especialmente información que pueda correlacionarse entre múltiples consultas.

---

# 23. Exploit

El solver completo implementa:

1. Conexión al servidor.
2. Obtención de `e`, `n`, `c`.
3. Generación de las dos cadenas de consultas.
4. Recolección de las Hamming Weights.
5. Recuperación de los bits de `m/n`.
6. Identificación de posiciones ambiguas.
7. Enumeración Gray Code.
8. Filtrado por `popcount`.
9. Filtrado mediante muestras adicionales.
10. Verificación RSA.
11. Envío del `m` recuperado.
12. Obtención de la flag.

```bash
python3 solve.py
```

---

# 24. TL;DR

Tenemos:

$$
c=m^e\bmod n
$$

Construimos:

$$
x_k=c2^{ek}\bmod n
$$

y obtenemos:

$$
x_k^d=m2^k\bmod n
$$

La oracle revela:

$$
w_k=HW(m2^k\bmod n)
$$

Construimos además:

$$
x'_k=n-x_k
$$

que revela:

$$
w'_k=HW(n-m2^k\bmod n)
$$

La evolución cumple:

$$
v_{k+1}=2v_k-b_kn
$$

Si:

```text
w  cambia
w' igual
```

entonces:

$$
b=1
$$

Si:

```text
w  igual
w' cambia
```

entonces:

$$
b=0
$$

Con esto recuperamos casi todos los bits de:

$$
\frac mn
$$

Los pocos bits ambiguos se fuerzan offline.

Finalmente:

$$
m^e\bmod n=c
$$

confirma el candidato correcto.

Enviamos `m`.

El servidor entrega la flag.

---

# Flag

```text
BHFlagY{...}
```
