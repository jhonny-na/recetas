from django.db import migrations, models
import recetasApp.models


class Migration(migrations.Migration):

    dependencies = [
        ('recetasApp', '0006_remove_receta_valoracion_cantidad_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='receta',
            name='chef',
            field=models.CharField(
                blank=True,
                choices=[('Catalina', 'Catalina'), ('Yesby', 'Yesby')],
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name='valoracion',
            name='nombre',
            field=models.CharField(
                max_length=100,
                validators=[recetasApp.models.validar_nombre_completo],
            ),
        ),
    ]
